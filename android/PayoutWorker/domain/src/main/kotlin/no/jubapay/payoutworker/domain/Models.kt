package no.jubapay.payoutworker.domain

import java.security.MessageDigest

enum class Phase {
 RECEIVED, VALIDATED, READY, PREPARING, SUBMISSION_POSSIBLE, AWAITING_CONFIRMATION,
 CONFIRMED_SUCCESS, CONFIRMED_NOT_PAID, UNKNOWN, RECONCILIATION_REQUIRED;
 val confirmed get() = this == CONFIRMED_SUCCESS || this == CONFIRMED_NOT_PAID
 val uncertain get() = this in setOf(SUBMISSION_POSSIBLE, AWAITING_CONFIRMATION, UNKNOWN, RECONCILIATION_REQUIRED)
 fun permits(next: Phase): Boolean = next in when(this) {
  RECEIVED -> setOf(VALIDATED, CONFIRMED_NOT_PAID, RECONCILIATION_REQUIRED)
  VALIDATED -> setOf(READY, CONFIRMED_NOT_PAID, RECONCILIATION_REQUIRED)
  READY -> setOf(PREPARING, CONFIRMED_NOT_PAID, RECONCILIATION_REQUIRED)
  PREPARING -> setOf(SUBMISSION_POSSIBLE, CONFIRMED_NOT_PAID, RECONCILIATION_REQUIRED)
  SUBMISSION_POSSIBLE -> setOf(AWAITING_CONFIRMATION, UNKNOWN, RECONCILIATION_REQUIRED)
  AWAITING_CONFIRMATION -> setOf(CONFIRMED_SUCCESS, CONFIRMED_NOT_PAID, UNKNOWN, RECONCILIATION_REQUIRED)
  UNKNOWN -> setOf(RECONCILIATION_REQUIRED)
  RECONCILIATION_REQUIRED -> setOf(CONFIRMED_SUCCESS, CONFIRMED_NOT_PAID)
  else -> emptySet()
 }
}
enum class ResultKind { SUCCESS_CONFIRMED, NOT_PAID_CONFIRMED, UNKNOWN }
enum class DeviceState { AVAILABLE, BUSY, PAUSED, DEGRADED, QUARANTINED, OFFLINE }
enum class Scenario { SUCCESS, REJECTION, DELAYED, UNKNOWN, NETWORK_BEFORE, NETWORK_AFTER, UNEXPECTED_MENU, DISABLED_ACCESSIBILITY }
data class Assignment(
 val payoutId: String, val attemptId: String, val deviceId: String, val assignmentVersion: Long,
 val providerId: String, val accountId: String, val simSubscriptionId: Int,
 val recipient: String, val recipientType: String, val amountMinor: Long, val currency: String,
 val payloadHash: String, val flowVersion: String, val claimExpiresAt: Long,
 val executionExpiresAt: Long, val correlationId: String, val scenario: Scenario = Scenario.SUCCESS
) {
 fun immutableHash(): String {
  // Versioned, unambiguous UTF-8 length-prefixed fields; matched by mock backend.
  val fields = listOf("1",payoutId,attemptId,deviceId,assignmentVersion.toString(),providerId,accountId,
   simSubscriptionId.toString(),recipient,recipientType,amountMinor.toString(),currency,flowVersion,
   claimExpiresAt.toString(),executionExpiresAt.toString(),correlationId,scenario.name)
  val bytes=fields.joinToString("") { "${it.toByteArray(Charsets.UTF_8).size}:$it" }.toByteArray(Charsets.UTF_8)
  return MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
 }
 fun validate(config: DeviceConfig, now: Long) {
  require(listOf(payoutId,attemptId,deviceId,accountId,correlationId).all { it.matches(Regex("[A-Za-z0-9_-]{1,100}")) }) { "INVALID_IDENTIFIERS" }
  require(assignmentVersion > 0 && amountMinor in 1..100_000_000_00L && currency == "USD") { "INVALID_MONEY" }
  require(recipientType == "MSISDN" && recipient.matches(if(providerId=="evc-plus") Regex("[0-9]{7,15}") else Regex("\\+[1-9][0-9]{7,14}"))) { "INVALID_RECIPIENT" }
  require(deviceId == config.deviceId && providerId == config.providerId && accountId == config.accountId && simSubscriptionId == config.simSubscriptionId) { "ASSIGNMENT_BINDING" }
  require((providerId == "simulator" && flowVersion == "sim-v1" && config.simulation) ||
   (providerId == "evc-plus" && flowVersion == "evc-712-v1" && !config.simulation && simSubscriptionId>=0)) { "UNAPPROVED_PROVIDER_FLOW" }
  require(now < claimExpiresAt && now < executionExpiresAt) { "ASSIGNMENT_EXPIRED" }
  require(payloadHash == immutableHash()) { "PAYLOAD_CONFLICT" }
 }
 val maskedRecipient get() = "••••${recipient.takeLast(4)}"
}
data class DeviceConfig(val deviceId: String, val providerId: String, val accountId: String, val simSubscriptionId: Int, val simulation: Boolean = true)
data class Authorization(val id: String, val attemptId: String, val payloadHash: String, val expiresAt: Long)
data class Evidence(val kind: ResultKind, val code: String, val reference: String? = null,
 val payloadHash: String? = null, val amountMinor: Long? = null, val currency: String? = null)
data class Attempt(val assignment: Assignment, val phase: Phase, val sequence: Long, val updatedAt: Long,
 val authorizationId: String? = null, val submissionAt: Long? = null, val evidence: Evidence? = null,
 val resultAcknowledged: Boolean = false)
data class Event(val eventId: String, val payoutId: String, val attemptId: String, val assignmentVersion: Long,
 val sequence: Long, val phase: Phase, val at: Long, val payloadHash: String, val evidence: Evidence?, val schemaVersion: Int = 1)
data class ReadinessCheck(val name: String, val ready: Boolean, val detail: String)
data class Control(val paused: Boolean = false, val drain: Boolean = false, val revoked: Boolean = false)
data class Reconciliation(val resolved: Boolean, val evidence: Evidence? = null, val auditId: String? = null)
sealed class WorkerFailure(message: String): Exception(message) {
 class Protocol(val code: String): WorkerFailure(code)
 class Authentication: WorkerFailure("AUTHENTICATION_REQUIRED")
 class Capacity: WorkerFailure("LOCAL_CAPACITY_REACHED")
 class Conflict: WorkerFailure("PAYLOAD_OR_STATE_CONFLICT")
 class NotReady: WorkerFailure("DEVICE_NOT_READY")
}
