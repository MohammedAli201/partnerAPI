package no.jubapay.payoutworker.data

import no.jubapay.payoutworker.domain.*
import org.json.JSONObject

object Wire {
 private fun JSONObject.exactLong(key:String):Long { val v=get(key); require(v is Long || v is Int) { "INTEGER_REQUIRED" }; return (v as Number).toLong() }
 fun assignment(j: JSONObject)=Assignment(j.getString("payout_id"),j.getString("attempt_id"),j.getString("device_id"),j.exactLong("assignment_version"),
  j.getString("provider_id"),j.getString("payout_account_id"),j.getInt("sim_subscription_id"),j.getString("recipient"),j.getString("recipient_type"),
  j.exactLong("amount_minor"),j.getString("currency"),j.getString("payload_hash"),j.getString("flow_version"),j.exactLong("claim_expires_at"),
  j.exactLong("execution_expires_at"),j.getString("correlation_id"),Scenario.valueOf(j.getString("scenario")))
 fun assignment(a: Assignment)=JSONObject().apply {
  put("payout_id",a.payoutId);put("attempt_id",a.attemptId);put("device_id",a.deviceId);put("assignment_version",a.assignmentVersion)
  put("provider_id",a.providerId);put("payout_account_id",a.accountId);put("sim_subscription_id",a.simSubscriptionId)
  put("recipient",a.recipient);put("recipient_type",a.recipientType);put("amount_minor",a.amountMinor);put("currency",a.currency)
  put("payload_hash",a.payloadHash);put("flow_version",a.flowVersion);put("claim_expires_at",a.claimExpiresAt)
  put("execution_expires_at",a.executionExpiresAt);put("correlation_id",a.correlationId);put("scenario",a.scenario.name)
 }
 fun evidence(e: Evidence)=JSONObject().apply { put("kind",e.kind.name);put("code",e.code);put("reference",e.reference);put("payload_hash",e.payloadHash);put("amount_minor",e.amountMinor);put("currency",e.currency) }
 fun evidence(j: JSONObject)=Evidence(ResultKind.valueOf(j.getString("kind")),j.getString("code"),j.optString("reference").ifBlank{null},
  j.optString("payload_hash").ifBlank{null},if(j.has("amount_minor"))j.exactLong("amount_minor")else null,j.optString("currency").ifBlank{null})
 fun event(e: Event)=JSONObject().apply {put("event_id",e.eventId);put("payout_id",e.payoutId);put("attempt_id",e.attemptId);put("assignment_version",e.assignmentVersion)
  put("sequence",e.sequence);put("phase",e.phase.name);put("at",e.at);put("payload_hash",e.payloadHash);put("schema_version",e.schemaVersion);put("evidence",e.evidence?.let(::evidence))}
 fun event(j: JSONObject)=Event(j.getString("event_id"),j.getString("payout_id"),j.getString("attempt_id"),j.exactLong("assignment_version"),j.exactLong("sequence"),
  Phase.valueOf(j.getString("phase")),j.exactLong("at"),j.getString("payload_hash"),j.optJSONObject("evidence")?.let(::evidence),j.getInt("schema_version"))
 fun config(j: JSONObject)=DeviceConfig(j.getString("device_id"),j.getString("provider_id"),j.getString("payout_account_id"),j.getInt("sim_subscription_id"),j.getBoolean("simulation"))
}
