import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onSchedule} from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";

// SM2アルゴリズムの実装
function calculateSM2(easinessFactor: number, repetition: number, interval: number, quality: number) {
  let newEasinessFactor = easinessFactor;
  let newRepetition = repetition;
  let newInterval = interval;

  if (quality >= 3) {
    if (repetition === 0) {
      newInterval = 1;
    } else if (repetition === 1) {
      newInterval = 6;
    } else {
      newInterval = Math.round(interval * easinessFactor);
    }
    newRepetition = repetition + 1;
  } else {
    newRepetition = 0;
    newInterval = 1;
  }

  newEasinessFactor = easinessFactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02));
  if (newEasinessFactor < 1.3) {
    newEasinessFactor = 1.3;
  }

  const nextReviewDate = new Date();
  nextReviewDate.setDate(nextReviewDate.getDate() + newInterval);

  return {
    easinessFactor: newEasinessFactor,
    repetition: newRepetition,
    interval: newInterval,
    nextReviewDate: nextReviewDate
  };
}
import * as admin from "firebase-admin";

admin.initializeApp();
const db = admin.firestore();

// === 最適化されたCloud Functions for Native App ===

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
    const {questionId, isCorrect, quality, responseTime} = data;

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
        study_time_minutes: admin.firestore.FieldValue.increment(responseTime ? responseTime / 60000 : 1)
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

// SM-2アルゴリズムの実装（最適化版）
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

// === Native App対応のAPI ===

export const getUserStudyData = onCall({region: "asia-northeast1"}, async (request) => {
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  
  try {
    // ユーザープロフィール取得
    const userDoc = await db.collection("users").doc(uid).get();
    const userData = userDoc.exists ? userDoc.data() || {} : {};
    
    // 今日の復習対象カード取得
    const today = admin.firestore.Timestamp.now();
    const dueCardsQuery = db.collection("study_cards")
      .where("uid", "==", uid)
      .where("sm2_data.due_date", "<=", today)
      .limit(10);
    
    const dueCardsSnapshot = await dueCardsQuery.get();
    const dueCards = dueCardsSnapshot.docs.map(doc => ({
      question_id: doc.data().question_id,
      due_date: doc.data().sm2_data.due_date,
      difficulty: doc.data().metadata.difficulty
    }));
    
    return {
      success: true,
      user: {
        uid: uid,
        profile: userData.profile || {},
        statistics: userData.statistics || {},
        permissions: userData.profile?.permissions || {}
      },
      study_data: {
        due_cards_count: dueCards.length,
        due_cards: dueCards
      },
      last_updated: admin.firestore.Timestamp.now()
    };
    
  } catch (error) {
    logger.error("Error in getUserStudyData:", error);
    throw new HttpsError("internal", "Failed to get user study data");
  }
});

export const submitStudySession = onCall({region: "asia-northeast1"}, async (request) => {
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError("unauthenticated", "User must be authenticated.");
  }

  const uid = request.auth.uid;
  const sessionData = request.data;
  
  try {
    // 学習セッション記録
    const sessionDoc = {
      uid: uid,
      session_id: sessionData.session_id,
      start_time: sessionData.start_time || admin.firestore.Timestamp.now(),
      end_time: sessionData.end_time || admin.firestore.Timestamp.now(),
      session_type: sessionData.session_type || "manual",
      questions: sessionData.questions || [],
      summary: sessionData.summary || {}
    };
    
    const sessionRef = await db.collection("study_sessions").add(sessionDoc);
    
    // 各問題のSM2データ更新
    for (const question of sessionData.questions || []) {
      const questionId = question.question_id;
      const quality = question.quality_rating || 3;
      
      logger.info(`Processing question ${questionId} with quality ${quality}`);
      
      // 直接SM2アルゴリズムを適用してFirestoreを更新
      const userQuestionRef = db.collection("user_questions").doc(`${request.auth?.uid}_${questionId}`);
      const userQuestionDoc = await userQuestionRef.get();
      
      if (userQuestionDoc.exists) {
        const data = userQuestionDoc.data();
        const sm2Result = calculateSM2(
          data?.easiness_factor || 2.5,
          data?.repetition_count || 0,
          data?.interval_days || 1,
          quality
        );
        
        await userQuestionRef.update({
          easiness_factor: sm2Result.easinessFactor,
          repetition_count: sm2Result.repetition,
          interval_days: sm2Result.interval,
          next_review_date: admin.firestore.Timestamp.fromDate(sm2Result.nextReviewDate),
          last_answered: admin.firestore.Timestamp.now()
        });
      }
    }
    
    return {
      success: true,
      session_id: sessionRef.id,
      message: "Study session recorded successfully"
    };
    
  } catch (error) {
    logger.error("Error in submitStudySession:", error);
    throw new HttpsError("internal", "Failed to submit study session");
  }
});

// === 日次集計（最適化版） ===

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
    
    // 前日の学習セッションを取得
    const sessionsQuery = db.collection("study_sessions")
      .where("start_time", ">=", admin.firestore.Timestamp.fromDate(new Date(dateKey)))
      .where("start_time", "<", admin.firestore.Timestamp.fromDate(new Date()));
    
    const sessionsSnapshot = await sessionsQuery.get();
    
    // ユーザー別の集計
    const userStats: { [uid: string]: any } = {};
    
    sessionsSnapshot.forEach((doc) => {
      const session = doc.data();
      const uid = session.uid;
      
      if (!userStats[uid]) {
        userStats[uid] = {
          questions_answered: 0,
          correct_answers: 0,
          study_time_minutes: 0,
          sessions_count: 0
        };
      }
      
      const summary = session.summary || {};
      userStats[uid].questions_answered += summary.total_questions || 0;
      userStats[uid].correct_answers += summary.correct_answers || 0;
      userStats[uid].study_time_minutes += summary.duration_minutes || 0;
      userStats[uid].sessions_count += 1;
    });
    
    // 各ユーザーの分析サマリーを更新
    const batch = db.batch();
    
    for (const [uid, stats] of Object.entries(userStats)) {
      const summaryRef = db.collection("analytics_summary").doc(`${uid}_daily_${dateKey}`);
      
      const accuracy = stats.questions_answered > 0 ? 
        (stats.correct_answers / stats.questions_answered * 100) : 0;
      
      batch.set(summaryRef, {
        uid: uid,
        period: "daily",
        date: dateKey,
        metrics: {
          questions_answered: stats.questions_answered,
          correct_answers: stats.correct_answers,
          accuracy: accuracy,
          study_time_minutes: stats.study_time_minutes,
          sessions_count: stats.sessions_count
        },
        weak_subjects: [], // 詳細分析は別途実装
        strong_subjects: [],
        updated_at: admin.firestore.Timestamp.now()
      });
    }
    
    await batch.commit();
    
    logger.info(`Aggregated analytics for ${Object.keys(userStats).length} users`);
    
  } catch (error) {
    logger.error("Error in daily analytics aggregation:", error);
    throw error;
  }
});

// === データクリーンアップ ===

export const cleanupOldData = onCall({region: "asia-northeast1"}, async (request) => {
  // 管理者権限チェック（実装は省略）
  
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
