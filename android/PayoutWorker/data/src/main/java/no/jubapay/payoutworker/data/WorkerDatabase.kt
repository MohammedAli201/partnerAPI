package no.jubapay.payoutworker.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Entity(tableName="attempts",indices=[Index(value=["payoutId"],unique=true)])
data class AttemptRow(@PrimaryKey val id: String,val payoutId: String,val payloadHash: String,val encryptedJob: String,
 val phase: String,val sequence: Long,val updatedAt: Long,val authorizationId: String?=null,val submissionAt: Long?=null,
 val encryptedEvidence: String?=null,val acknowledged: Boolean=false)
@Entity(tableName="outbox",indices=[Index(value=["attemptId","sequence"],unique=true)])
data class OutboxRow(@PrimaryKey val id: String,val attemptId: String,val sequence: Long,val encryptedEvent: String)
@Entity(tableName="control") data class ControlRow(@PrimaryKey val id: Int=1,val activeAttempt: String?=null,val quarantine: String?=null)
@Dao interface WorkerDao {
 @Query("SELECT * FROM attempts ORDER BY updatedAt DESC") fun observe(): Flow<List<AttemptRow>>
 @Query("SELECT * FROM attempts ORDER BY updatedAt DESC") suspend fun all(): List<AttemptRow>
 @Query("SELECT * FROM attempts WHERE id=:id") suspend fun get(id: String): AttemptRow?
 @Query("SELECT * FROM attempts WHERE payoutId=:id") suspend fun payout(id: String): AttemptRow?
 @Insert suspend fun insert(row: AttemptRow)
 @Update suspend fun update(row: AttemptRow)
 @Insert suspend fun event(row: OutboxRow)
 @Query("SELECT * FROM outbox ORDER BY attemptId,sequence LIMIT 128") suspend fun events(): List<OutboxRow>
 @Query("SELECT * FROM outbox WHERE id=:id") suspend fun event(id: String): OutboxRow?
 @Query("DELETE FROM outbox WHERE id=:id") suspend fun deleteEvent(id: String)
 @Query("SELECT COUNT(*) FROM attempts") suspend fun count(): Int
 @Query("SELECT COUNT(*) FROM outbox") suspend fun pendingCount(): Int
 @Query("SELECT * FROM control WHERE id=1") suspend fun control(): ControlRow?
 @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun control(row: ControlRow)
}
@Database(entities=[AttemptRow::class,OutboxRow::class,ControlRow::class],version=1,exportSchema=true)
abstract class WorkerDatabase: RoomDatabase() { abstract fun dao(): WorkerDao }
