package no.jubapay.payoutworker

import no.jubapay.payoutworker.domain.*

/** Retains old attempt uploads; real modem diagnostics use ManualUssdTest directly. */
class ReportingOnlyProvider: ProviderAdapter {
 override val providerId="diagnostic-only"
 override val flowVersion="ussd-test-v1"
 override val submissionBoundary="Operator confirms a backend-issued USSD diagnostic"
 override suspend fun readiness(job:Assignment)=listOf(ReadinessCheck("Payout execution",false,"Use real SIM USSD test"))
 override suspend fun prepare(job:Assignment):Unit=throw WorkerFailure.Protocol("PAYOUT_EXECUTION_DISABLED")
 override suspend fun executeSubmission(job:Assignment):Evidence=throw WorkerFailure.Protocol("PAYOUT_EXECUTION_DISABLED")
 override fun interpret(job:Assignment,evidence:Evidence)=Evidence(ResultKind.UNKNOWN,"HistoricalResultRequiresReview")
 override suspend fun captureEvidence(job:Assignment):Evidence?=null
 override suspend fun recover(job:Assignment):Evidence?=null
 override suspend fun cancelBeforeSubmission(job:Assignment) {}
}
