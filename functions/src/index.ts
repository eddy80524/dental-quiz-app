import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onSchedule} from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import * as admin from "firebase-admin";

admin.initializeApp();
const db = admin.firestore();

// === 最適化されたCloud Functions ===

export const getDailyQuiz = onCall({region: "asia-northeast1"}, async (request) => {
  logger.info("Optimized getDailyQuiz: Received auth object:", request.auth);

  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  logger.info(`Processing optimized getDailyQuiz for user: ${uid}`);

  try {
    // 最適化されたスキーマから復習対象カード取得
    const today = admin.firestore.Timestamp.now();
    
    const studyCardsQuery = db.collection("study_cards")
      .where("uid", "==", uid)
      .where("sm2_data.due_date", "<=", today)
      .orderBy("sm2_data.due_date")
      .limit(20);
    
    const studyCardsSnapshot = await studyCardsQuery.get();
    
    logger.info(`User ${uid}: Found ${studyCardsSnapshot.size} due study cards.`);
    
    const reviewQuestionIds: string[] = [];
    studyCardsSnapshot.forEach((doc) => {
      const cardData = doc.data();
      reviewQuestionIds.push(cardData.question_id);
    });
    
    // 新規問題選択（簡易版）
    const newQuestionIds: string[] = [];
    
    const allQuestionIds = [...reviewQuestionIds, ...newQuestionIds];
    
    logger.info(`User ${uid}: Returning ${allQuestionIds.length} questions (${reviewQuestionIds.length} review, ${newQuestionIds.length} new)`);
    
    return {
      success: true,
      questionIds: allQuestionIds,
      reviewCount: reviewQuestionIds.length,
      newCount: newQuestionIds.length,
      // 後方互換性のため
      reviewCards: reviewQuestionIds,
      newCards: newQuestionIds,
    };

  } catch (error) {
    logger.error("Error in optimized getDailyQuiz for user:", uid, error);
    throw new HttpsError(
      "internal",
      "An error occurred while fetching the quiz."
    );
  }
});

export const logStudyActivity = onCall({region: "asia-northeast1"}, async (request) => {
  logger.info("Optimized logStudyActivity: Received auth object:", request.auth);

  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  const data = request.data;
  
  logger.info(`Optimized logStudyActivity: Processing request for user: ${uid}`, data);

  try {
    const {questionId, isCorrect, quality} = data;

    if (!questionId || quality === undefined) {
      throw new HttpsError("invalid-argument", "questionId and quality are required.");
    }

    // 最適化されたスキーマのstudy_cardsコレクションを更新
    const cardId = `${uid}_${questionId}`;
    const cardRef = db.collection("study_cards").doc(cardId);
    const cardDoc = await cardRef.get();
    
    let cardData: any;
    if (cardDoc.exists) {
      cardData = cardDoc.data();
      logger.info(`logStudyActivity: Found existing card for ${questionId}`);
    } else {
      // 新しいカードの場合、初期データを作成
      cardData = {
        uid: uid,
        question_id: questionId,
        sm2_data: {
          n: 0,
          ef: 2.5,
          interval: 0,
          due_date: admin.firestore.Timestamp.now(),
          last_studied: null
        },
        performance: {
          total_attempts: 0,
          correct_attempts: 0,
          avg_quality: 0.0,
          last_quality: 0
        },
        metadata: {
          created_at: admin.firestore.Timestamp.now(),
          updated_at: admin.firestore.Timestamp.now(),
          subject: "未分類",
          difficulty: "normal"
        }
      };
      logger.info(`logStudyActivity: Creating new card for ${questionId}`);
    }

    // SM-2アルゴリズムに基づく更新処理
    const now = admin.firestore.Timestamp.now();
    const updatedSM2 = performSM2Update(cardData.sm2_data, quality, now);
    
    // パフォーマンスデータ更新
    const performance = cardData.performance;
    const newTotalAttempts = performance.total_attempts + 1;
    const newCorrectAttempts = performance.correct_attempts + (isCorrect ? 1 : 0);
    const newAvgQuality = (performance.avg_quality * performance.total_attempts + quality) / newTotalAttempts;
    
    const updatedCard = {
      ...cardData,
      sm2_data: updatedSM2,
      performance: {
        total_attempts: newTotalAttempts,
        correct_attempts: newCorrectAttempts,
        avg_quality: newAvgQuality,
        last_quality: quality
      },
      metadata: {
        ...cardData.metadata,
        updated_at: now
      }
    };

    // カードデータを更新
    await cardRef.set(updatedCard);
    logger.info(`logStudyActivity: Updated study card ${questionId} for user ${uid}`);

    // 日次分析サマリー更新
    const today = new Date().toISOString().split('T')[0];
    const dailySummaryRef = db.collection("analytics_summary").doc(`${uid}_daily_${today}`);
    
    await dailySummaryRef.set({
      uid: uid,
      period: "daily",
      date: today,
      metrics: {
        questions_answered: admin.firestore.FieldValue.increment(1),
        correct_answers: admin.firestore.FieldValue.increment(isCorrect ? 1 : 0),
        study_time_minutes: admin.firestore.FieldValue.increment(1)
      },
      updated_at: now
    }, { merge: true });

    // ユーザー統計更新
    await db.collection("users").doc(uid).update({
      "statistics.total_questions_answered": admin.firestore.FieldValue.increment(1),
      "statistics.total_correct_answers": admin.firestore.FieldValue.increment(isCorrect ? 1 : 0),
      "statistics.last_study_date": today
    });

    logger.info(`logStudyActivity: Successfully logged activity for user ${uid}`);

    return {
      success: true,
      updatedCard: updatedCard
    };

  } catch (error) {
    logger.error("Error in optimized logStudyActivity for user:", uid, error);
    throw new HttpsError(
      "internal",
      "An error occurred while logging study activity."
    );
  }
});

// === ユーザー学習データ取得 ===

export const getUserStudyData = onCall({region: "asia-northeast1"}, async (request) => {
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;

  try {
    // ユーザー基本情報
    const userDoc = await db.collection("users").doc(uid).get();
    if (!userDoc.exists) {
      throw new HttpsError("not-found", "User not found.");
    }

    // 復習対象カード数
    const today = admin.firestore.Timestamp.now();
    const dueCardsSnapshot = await db.collection("study_cards")
      .where("uid", "==", uid)
      .where("sm2_data.due_date", "<=", today)
      .get();

    // 今日の学習統計
    const todayKey = new Date().toISOString().split('T')[0];
    const todayStatsDoc = await db.collection("analytics_summary")
      .doc(`${uid}_daily_${todayKey}`)
      .get();

    const todayStats = todayStatsDoc.exists ? todayStatsDoc.data()?.metrics : {
      questions_answered: 0,
      correct_answers: 0,
      study_time_minutes: 0
    };

    return {
      success: true,
      userData: userDoc.data(),
      dueCardsCount: dueCardsSnapshot.size,
      todayStats: todayStats
    };

  } catch (error) {
    logger.error("Error in getUserStudyData:", error);
    throw new HttpsError("internal", "Failed to get user study data");
  }
});

// === 学習セッション記録 ===

export const submitStudySession = onCall({region: "asia-northeast1"}, async (request) => {
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  const {sessionId, responses, startTime, endTime} = request.data;

  try {
    const now = admin.firestore.Timestamp.now();
    
    // 学習セッションを記録
    const sessionData = {
      uid: uid,
      session_id: sessionId,
      start_time: admin.firestore.Timestamp.fromDate(new Date(startTime)),
      end_time: admin.firestore.Timestamp.fromDate(new Date(endTime)),
      total_questions: responses.length,
      correct_answers: responses.filter((r: any) => r.isCorrect).length,
      responses: responses,
      created_at: now
    };

    await db.collection("study_sessions").doc(sessionId).set(sessionData);

    // 各問題の回答を処理
    const batch = db.batch();
    
    for (const response of responses) {
      const cardId = `${uid}_${response.questionId}`;
      // バッチ処理での更新（実装は簡略化）
      logger.info(`Processing response for card: ${cardId}`);
    }

    await batch.commit();

    return {
      success: true,
      sessionId: sessionId,
      processed: responses.length
    };

  } catch (error) {
    logger.error("Error in submitStudySession:", error);
    throw new HttpsError("internal", "Failed to submit study session");
  }
});

// === SM-2アルゴリズムの実装 ===

function performSM2Update(sm2Data: any, quality: number, now: admin.firestore.Timestamp): any {
  let n = sm2Data.n || 0;
  let ef = sm2Data.ef || 2.5;
  let interval = sm2Data.interval || 0;

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

  return {
    n: n,
    ef: ef,
    interval: interval,
    due_date: admin.firestore.Timestamp.fromDate(nextReviewDate),
    last_studied: now
  };
}

// === 日次集計 ===

export const aggregateDailyAnalytics = onSchedule({
  schedule: "0 3 * * *", // 毎日午前3時
  timeZone: "Asia/Tokyo",
  region: "asia-northeast1"
}, async (event) => {
  logger.info("Starting optimized daily analytics aggregation...");

  try {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const dateKey = yesterday.toISOString().split('T')[0];
    
    // 前日の学習データを集計
    const analyticsQuery = db.collection("analytics_summary")
      .where("period", "==", "daily")
      .where("date", "==", dateKey);
    
    const analyticsSnapshot = await analyticsQuery.get();
    
    logger.info(`Found ${analyticsSnapshot.size} daily summaries for ${dateKey}`);
    
    // 集計処理の実装（詳細は省略）
    
  } catch (error) {
    logger.error("Error in daily analytics aggregation:", error);
    throw error;
  }
});

// === データクリーンアップ ===

export const cleanupOldData = onCall({region: "asia-northeast1"}, async (request) => {
  try {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - 90); // 90日前
    
    // 古い分析データを削除
    const oldAnalyticsQuery = db.collection("analytics_summary")
      .where("updated_at", "<", admin.firestore.Timestamp.fromDate(cutoffDate))
      .limit(500);
    
    const oldDocs = await oldAnalyticsQuery.get();
    
    const batch = db.batch();
    oldDocs.forEach((doc) => {
      batch.delete(doc.ref);
    });
    
    await batch.commit();
    
    return {
      success: true,
      deleted_count: oldDocs.size,
      message: "Old data cleaned up successfully"
    };
    
  } catch (error) {
    logger.error("Error in data cleanup:", error);
    throw new HttpsError("internal", "Failed to cleanup old data");
  }
});

// === 管理者用分析機能 ===

export const getSystemAnalytics = onCall({region: "asia-northeast1"}, async (request) => {
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  try {
    // 管理者権限チェック（簡略化）
    const userDoc = await db.collection("users").doc(request.auth.uid).get();
    const userData = userDoc.data();
    
    if (!userData?.role || userData.role !== "admin") {
      throw new HttpsError("permission-denied", "Admin access required.");
    }

    // システム全体の統計を取得
    const today = new Date().toISOString().split('T')[0];
    
    const todayAnalytics = await db.collection("analytics_summary")
      .where("period", "==", "daily")
      .where("date", "==", today)
      .get();
    
    let totalQuestions = 0;
    let totalCorrect = 0;
    let activeUsers = 0;
    
    todayAnalytics.forEach((doc) => {
      const metrics = doc.data().metrics;
      totalQuestions += metrics.questions_answered || 0;
      totalCorrect += metrics.correct_answers || 0;
      if (metrics.questions_answered > 0) {
        activeUsers++;
      }
    });

    return {
      success: true,
      analytics: {
        date: today,
        total_questions: totalQuestions,
        total_correct: totalCorrect,
        accuracy_rate: totalQuestions > 0 ? (totalCorrect / totalQuestions) : 0,
        active_users: activeUsers
      }
    };

  } catch (error) {
    logger.error("Error in getSystemAnalytics:", error);
    throw new HttpsError("internal", "Failed to get system analytics");
  }
});
