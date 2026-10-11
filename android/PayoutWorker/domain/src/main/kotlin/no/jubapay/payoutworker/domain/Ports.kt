package no.jubapay.payoutworker.domain

import kotlinx.coroutines.flow.Flow

interface AttemptStore {
 val changes: Flow<List<Attempt>>
 suspend fun accept(job: Assignment): Attempt
 suspend fun get(id: String): Attempt?
 suspend fun all(): List<Attempt>
 suspend fun transition(id: String, expected: Phase, next: Phase, evidence: Evidence? = null, authorization: Authorization? = null): Attempt
 suspend fun pending(): List<Event>
 suspend fun acknowledge(eventId: String)
 suspend fun quarantine(reason: String)
 suspend fun quarantineReason(): String?
 suspend fun clearQuarantineAfterReconciliation()
 suspend fun hasCapacity(): Boolean
}
interface Backend {
 suspend fun heartbeat(state: DeviceState): Control
 suspend fun claim(): Assignment?
 suspend fun acknowledgeAssignment(job: Assignment)
 suspend fun authorize(job: Assignment): Authorization
 suspend fun upload(event: Event): Boolean
 suspend fun reconcile(attempt: Attempt): Reconciliation
}
interface ProviderAdapter {
 val providerId: String
 val flowVersion: String
 val submissionBoundary: String
 suspend fun readiness(job: Assignment): List<ReadinessCheck>
 suspend fun prepare(job: Assignment)
 suspend fun executeSubmission(job: Assignment): Evidence
 fun interpret(job: Assignment, evidence: Evidence): Evidence
 suspend fun captureEvidence(job: Assignment): Evidence?
 suspend fun cancelBeforeSubmission(job: Assignment)
 suspend fun recover(job: Assignment): Evidence?
}
fun interface Readiness { suspend fun checks(): List<ReadinessCheck> }
fun interface TimeSource { fun now(): Long }
