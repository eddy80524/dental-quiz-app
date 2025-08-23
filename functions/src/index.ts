import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onSchedule} from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import * as admin from "firebase-admin";

admin.initializeApp();
const db = admin.firestore();

export const getDailyQuiz = onCall({region: "asia-northeast1"}, (request) => {
  logger.info("Received auth object:", request.auth);

  // 認証チェック：uidが存在しない場合はエラー
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  logger.info(`Processing request for user: ${uid}`);

  return db.collection("users").doc(uid).collection("userCards").get()
    .then((cardsSnapshot) => {
      logger.info(`User ${uid}: Found ${cardsSnapshot.size} userCards documents.`);

      if (cardsSnapshot.empty) {
        logger.warn(`User ${uid}: No userCards found. Returning empty arrays.`);
        return {
          reviewCards: [],
          newCards: [],
        };
      }

      const userCards: { [key: string]: any } = {};
      cardsSnapshot.forEach((doc) => {
        userCards[doc.id] = doc.data();
        logger.info(`User ${uid}: Card ${doc.id} data:`, doc.data());
      });

      const today = new Date();
      today.setHours(0, 0, 0, 0);
      logger.info(`User ${uid}: Today date for comparison:`, today.toISOString());

      const reviewCardIds = Object.keys(userCards).filter((cardId) => {
        const card = userCards[cardId];
        const reviewDateField = card.nextReview || card.due;

        if (reviewDateField) {
          try {
            let reviewDate: Date;
            
            // Firestoreタイムスタンプかどうかチェック
            if (reviewDateField && typeof reviewDateField.toDate === 'function') {
              reviewDate = reviewDateField.toDate();
            } 
            // 文字列の場合
            else if (typeof reviewDateField === 'string') {
              reviewDate = new Date(reviewDateField);
            }
            // 数値の場合（Unix timestamp）
            else if (typeof reviewDateField === 'number') {
              reviewDate = new Date(reviewDateField);
            }
            // Dateオブジェクトの場合
            else if (reviewDateField instanceof Date) {
              reviewDate = reviewDateField;
            }
            // その他のオブジェクトの場合（seconds/nanoseconds形式など）
            else if (reviewDateField && typeof reviewDateField === 'object') {
              if (reviewDateField.seconds) {
                reviewDate = new Date(reviewDateField.seconds * 1000);
              } else if (reviewDateField._seconds) {
                reviewDate = new Date(reviewDateField._seconds * 1000);
              } else {
                logger.error(`User ${uid}: Unknown date format for card ${cardId}:`, reviewDateField);
                return false;
              }
            } else {
              logger.error(`User ${uid}: Invalid date format for card ${cardId}:`, reviewDateField);
              return false;
            }
            
            logger.info(`User ${uid}: Card ${cardId} review date:`, reviewDate.toISOString(), "vs today:", today.toISOString());
            return reviewDate <= today;
          } catch (error) {
            logger.error(`User ${uid}: Error parsing date for card ${cardId}:`, error, "Date field:", reviewDateField);
            return false;
          }
        } else {
          logger.info(`User ${uid}: Card ${cardId} has no nextReview or due field`);
          return false;
        }
      });

      const newCardIds: string[] = [];

      logger.info(`User ${uid}: Found ${reviewCardIds.length} review cards.`);
      
      // Python側で期待されている形式でレスポンスを返す
      const allQuestionIds = [...reviewCardIds, ...newCardIds];
      
      return {
        success: true,
        questionIds: allQuestionIds,
        reviewCount: reviewCardIds.length,
        newCount: newCardIds.length,
        // 後方互換性のため古い形式も保持
        reviewCards: reviewCardIds,
        newCards: newCardIds,
      };
    })
    .catch((error) => {
      logger.error("Error in getDailyQuiz for user:", uid, error);
      throw new HttpsError(
        "internal",
        "An error occurred while fetching the quiz."
      );
    });
});

export const logStudyActivity = onCall({region: "asia-northeast1"}, async (request) => {
  logger.info("logStudyActivity: Received auth object:", request.auth);

  // 認証チェック：uidが存在しない場合はエラー
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  const data = request.data;
  
  logger.info(`logStudyActivity: Processing request for user: ${uid}`, data);

  try {
    const {questionId, isCorrect, isNewCard, quality, cardLevelChange} = data;

    if (!questionId || quality === undefined) {
      throw new HttpsError("invalid-argument", "questionId and quality are required.");
    }

    // 現在のカードデータを取得
    const cardRef = db.collection("users").doc(uid).collection("userCards").doc(questionId);
    const cardDoc = await cardRef.get();
    
    let cardData: any;
    if (cardDoc.exists) {
      cardData = cardDoc.data();
      logger.info(`logStudyActivity: Found existing card for ${questionId}:`, cardData);
    } else {
      // 新しいカードの場合、初期データを作成
      cardData = {
        n: 0,
        ef: 2.5,
        interval: 1,
        level: 0,
        lastStudied: null,
        nextReview: null,
        history: []
      };
      logger.info(`logStudyActivity: Creating new card for ${questionId}`);
    }

    // SM-2アルゴリズムに基づく更新処理
    const now = admin.firestore.Timestamp.now();
    const updatedCard = performSM2Update(cardData, quality, now);
    
    // 学習ログエントリを作成（undefined値を避けるため、デフォルト値を設定）
    const logEntry = {
      timestamp: now,
      isCorrect: isCorrect,
      quality: quality,
      cardLevelChange: cardLevelChange,
      isNewCard: isNewCard,
      intervalBefore: cardData.interval || 1,
      intervalAfter: updatedCard.interval || 1,
      efBefore: cardData.ef || 2.5,
      efAfter: updatedCard.ef || 2.5
    };

    // historyに追加
    if (!updatedCard.history) {
      updatedCard.history = [];
    }
    updatedCard.history.push(logEntry);

    // カードデータを更新
    await cardRef.set(updatedCard);
    logger.info(`logStudyActivity: Updated card ${questionId} for user ${uid}`);

    // daily_learning_logsに学習ログを保存
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dateKey = today.toISOString().split('T')[0]; // YYYY-MM-DD形式

    const logRef = db.collection("daily_learning_logs").doc(`${uid}_${dateKey}`);
    
    await logRef.set({
      userId: uid,
      date: dateKey,
      activities: admin.firestore.FieldValue.arrayUnion({
        questionId: questionId,
        timestamp: now,
        isCorrect: isCorrect,
        quality: quality,
        cardLevelChange: cardLevelChange,
        isNewCard: isNewCard
      })
    }, { merge: true });

    logger.info(`logStudyActivity: Saved daily log for user ${uid} on ${dateKey}`);

    return {
      success: true,
      updatedCard: updatedCard
    };

  } catch (error) {
    logger.error("Error in logStudyActivity for user:", uid, error);
    throw new HttpsError(
      "internal",
      "An error occurred while logging study activity."
    );
  }
});

// SM-2アルゴリズムの実装
function performSM2Update(card: any, quality: number, now: admin.firestore.Timestamp): any {
  const updatedCard = { ...card };
  
  // 現在の値を取得（デフォルト値設定）
  let n = updatedCard.n || 0;
  let ef = updatedCard.ef || 2.5;
  let interval = updatedCard.interval || 1;

  if (quality >= 3) {
    // 正解の場合
    if (n === 0) {
      interval = 1;
    } else if (n === 1) {
      interval = 6;
    } else {
      interval = Math.round(interval * ef);
    }
    n += 1;
  } else {
    // 不正解の場合
    n = 0;
    interval = 1;
  }

  // EFの更新
  ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
  if (ef < 1.3) {
    ef = 1.3;
  }

  // 次回復習日を計算
  const nextReviewDate = new Date(now.toDate());
  nextReviewDate.setDate(nextReviewDate.getDate() + interval);

  // カードデータを更新
  updatedCard.n = n;
  updatedCard.ef = ef;
  updatedCard.interval = interval;
  updatedCard.lastStudied = now;
  updatedCard.nextReview = admin.firestore.Timestamp.fromDate(nextReviewDate);
  updatedCard.level = Math.max(0, (updatedCard.level || 0) + (quality >= 3 ? 1 : -1));

  return updatedCard;
}

// ランキング集計システム

// 毎日午前3時にランキング集計を実行
export const aggregateDailyRankings = onSchedule({
  schedule: "0 3 * * *", // 毎日午前3時
  timeZone: "Asia/Tokyo",
  region: "asia-northeast1"
}, async (event) => {
  logger.info("Starting daily rankings aggregation...");

  try {
    // 過去24時間分のログを取得
    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    
    // 日付キーフォーマット (YYYY-MM-DD)
    const todayKey = now.toISOString().split('T')[0];
    const yesterdayKey = yesterday.toISOString().split('T')[0];
    
    logger.info(`Aggregating logs for dates: ${yesterdayKey} and ${todayKey}`);

    // 過去24時間分のログを取得
    const logsSnapshot = await db.collection("daily_learning_logs")
      .where("date", "in", [todayKey, yesterdayKey])
      .get();

    logger.info(`Found ${logsSnapshot.size} daily learning log documents`);

    if (logsSnapshot.empty) {
      logger.info("No learning logs found for the past 24 hours");
      return;
    }

    // ユーザー別の集計データ
    const userStats: { [userId: string]: UserDailyStats } = {};

    // ログデータを集計
    logsSnapshot.forEach((doc) => {
      const logData = doc.data();
      const userId = logData.userId;
      const activities = logData.activities || [];

      if (!userStats[userId]) {
        userStats[userId] = {
          totalQuestions: 0,
          correctAnswers: 0,
          dailyPoints: 0,
          masteryScore: 0,
          studyStreak: 0
        };
      }

      // 各学習活動を処理
      activities.forEach((activity: any) => {
        // 24時間以内の活動のみをカウント
        const activityTime = activity.timestamp.toDate();
        if (activityTime >= yesterday) {
          userStats[userId].totalQuestions++;
          
          if (activity.isCorrect) {
            userStats[userId].correctAnswers++;
          }

          // ポイント計算
          const points = calculatePoints(activity);
          userStats[userId].dailyPoints += points;
        }
      });

      // 習熟度スコア計算
      if (userStats[userId].totalQuestions > 0) {
        const accuracy = userStats[userId].correctAnswers / userStats[userId].totalQuestions;
        userStats[userId].masteryScore = accuracy * 100;
      }
    });

    logger.info(`Aggregated stats for ${Object.keys(userStats).length} users`);

    // 各ユーザーのプロフィールを更新
    const batch = db.batch();
    let updateCount = 0;

    for (const [userId, stats] of Object.entries(userStats)) {
      const profileRef = db.collection("user_profiles").doc(userId);
      
      // 既存のプロフィールデータを取得
      const profileDoc = await profileRef.get();
      const currentData = profileDoc.exists ? profileDoc.data() : {};

      // 更新データを準備
      const updateData = {
        lastUpdated: admin.firestore.Timestamp.now(),
        // 新規プロフィールのデフォルト設定
        nickname: currentData?.nickname || "匿名ユーザー",
        showOnLeaderboard: true, // 全ユーザー強制参加
        hasWeeklyActivity: true, // 今日学習活動があったのでアクティブフラグを設定
        dailyStats: {
          date: todayKey,
          totalQuestions: stats.totalQuestions,
          correctAnswers: stats.correctAnswers,
          accuracy: stats.masteryScore,
          pointsEarned: stats.dailyPoints
        },
        // 累積データの更新
        totalPoints: (currentData?.totalPoints || 0) + stats.dailyPoints,
        weeklyPoints: (currentData?.weeklyPoints || 0) + stats.dailyPoints,
        totalQuestions: (currentData?.totalQuestions || 0) + stats.totalQuestions,
        totalCorrectAnswers: (currentData?.totalCorrectAnswers || 0) + stats.correctAnswers,
        // 現在の習熟度スコア
        currentMasteryScore: stats.masteryScore,
        // 学習日数の更新
        studyDays: (currentData?.studyDays || 0) + (stats.totalQuestions > 0 ? 1 : 0)
      };

      batch.set(profileRef, updateData, { merge: true });
      updateCount++;
    }

    // バッチコミット
    await batch.commit();
    
    logger.info(`Successfully updated ${updateCount} user profiles`);

  } catch (error) {
    logger.error("Error in daily rankings aggregation:", error);
    throw error;
  }
});

// 毎週月曜日午前4時にweeklyPointsをリセット
export const resetWeeklyPoints = onSchedule({
  schedule: "0 4 * * 1", // 毎週月曜日午前4時
  timeZone: "Asia/Tokyo",
  region: "asia-northeast1"
}, async (event) => {
  logger.info("Starting weekly points reset...");

  try {
    // 全ユーザープロフィールを取得
    const profilesSnapshot = await db.collection("user_profiles").get();
    
    logger.info(`Found ${profilesSnapshot.size} user profiles to reset`);

    if (profilesSnapshot.empty) {
      logger.info("No user profiles found to reset");
      return;
    }

    // バッチ処理でweeklyPointsをリセット
    const batch = db.batch();
    let resetCount = 0;

    profilesSnapshot.forEach((doc) => {
      const profileRef = doc.ref;
      batch.update(profileRef, {
        weeklyPoints: 0,
        hasWeeklyActivity: false, // 週間活動フラグもリセット
        weeklyResetDate: admin.firestore.Timestamp.now()
      });
      resetCount++;
    });

    // バッチコミット
    await batch.commit();
    
    logger.info(`Successfully reset weekly points for ${resetCount} users`);

  } catch (error) {
    logger.error("Error in weekly points reset:", error);
    throw error;
  }
});

// ポイント計算ロジック
function calculatePoints(activity: any): number {
  let basePoints = 0;

  // 正解による基本ポイント
  if (activity.isCorrect) {
    basePoints = 10;
  } else {
    basePoints = 2; // 不正解でも参加ポイント
  }

  // 質評価による倍率
  const qualityMultiplier = {
    1: 0.5,  // もう一度
    2: 0.8,  // 難しい
    4: 1.0,  // 普通
    5: 1.5   // 簡単
  };

  const multiplier = qualityMultiplier[activity.quality as keyof typeof qualityMultiplier] || 1.0;
  
  // 新規カードボーナス
  const newCardBonus = activity.isNewCard ? 5 : 0;

  return Math.floor(basePoints * multiplier + newCardBonus);
}

// ユーザー統計の型定義
interface UserDailyStats {
  totalQuestions: number;
  correctAnswers: number;
  dailyPoints: number;
  masteryScore: number;
  studyStreak: number;
}
