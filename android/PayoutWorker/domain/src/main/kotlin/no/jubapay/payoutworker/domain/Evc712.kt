package no.jubapay.payoutworker.domain

import java.math.BigDecimal

/** Versioned local operator grammar, never arbitrary backend instructions. No PIN or raw prompt is retained. */
class Evc712Parser(private val observedSuccessTemplates: List<String> = emptyList()) {
    enum class Prompt { MATCH, MISMATCH, UNRECOGNIZED }
    private val prompt = Regex("^Uwareeji \\$([0-9]+(?:\\.[0-9]{1,2})?) [^()\\r\\n]+ \\(([0-9]{7,15})\\), Fadlan[.\\s]+Geli[.\\s]+PIN-kaaga[.\\s]*$")

    fun validate(job: Assignment) {
        require(job.providerId == "evc-plus" && job.flowVersion == "evc-712-v1")
        require(job.currency == "USD" && job.amountMinor in 1..10_000_000_000L)
        // No implicit +252 stripping: the canonical backend number must equal the operator prompt.
        require(job.recipient.matches(Regex("[0-9]{7,15}")))
        require(job.payloadHash == job.immutableHash())
    }

    fun command(job: Assignment): String {
        validate(job)
        return "*712*${job.recipient}*${amount(job.amountMinor)}#"
    }

    fun verifyPrompt(job: Assignment, text: String): Prompt {
        if(text.length>4096)return Prompt.UNRECOGNIZED
        val match = prompt.matchEntire(normalize(text)) ?: return Prompt.UNRECOGNIZED
        val minor = minor(match.groupValues[1]) ?: return Prompt.UNRECOGNIZED
        return if (minor == job.amountMinor && match.groupValues[2] == job.recipient) Prompt.MATCH else Prompt.MISMATCH
    }

    fun finalResult(job: Assignment, text: String): Evidence {
        if(text.length>4096)return Evidence(ResultKind.UNKNOWN,"UnrecognizedResponse")
        val normalized = normalize(text)
        if (normalized.trimEnd('.') == "Haraaga xisaabtaadu kuguma filna") {
            return Evidence(ResultKind.NOT_PAID_CONFIRMED,"InsufficientBalance",payloadHash=job.payloadHash,
                amountMinor=job.amountMinor,currency=job.currency)
        }
        // No production success example has been supplied. Empty configuration NEVER succeeds.
        for (template in observedSuccessTemplates) {
            val pattern = successPattern(template) ?: continue
            val result = pattern.matchEntire(normalized) ?: continue
            if (result.groups["recipient"]?.value != job.recipient || minor(result.groups["amount"]!!.value) != job.amountMinor) continue
            return Evidence(ResultKind.SUCCESS_CONFIRMED,"EvcSuccess",if(template.contains("{reference}"))result.groups["reference"]?.value else null,
                job.payloadHash,job.amountMinor,job.currency)
        }
        return Evidence(ResultKind.UNKNOWN,"UnrecognizedResponse")
    }

    private fun successPattern(template: String): Regex? {
        if(template.length !in 1..1000 || template.countToken("{amount}")!=1 || template.countToken("{recipient}")!=1 || template.countToken("{reference}")>1) return null
        val parts=Regex("\\{(?:amount|recipient|reference)\\}")
        val pattern=StringBuilder("^");var end=0
        for(match in parts.findAll(normalize(template))) {
            pattern.append(Regex.escape(normalize(template).substring(end,match.range.first)))
            pattern.append(when(match.value) {
                "{amount}" -> "(?<amount>[0-9]+(?:\\.[0-9]{1,2})?)"
                "{recipient}" -> "(?<recipient>[0-9]{7,15})"
                else -> "(?<reference>[A-Za-z0-9_-]{1,100})"
            });end=match.range.last+1
        }
        pattern.append(Regex.escape(normalize(template).substring(end))).append("$")
        return Regex(pattern.toString())
    }
    private fun String.countToken(token:String)=windowed(token.length).count{it==token}
    private fun normalize(text:String)=text.trim().replace(Regex("\\s+")," ")
    private fun minor(value:String):Long?=try{BigDecimal(value).movePointRight(2).longValueExact()}catch(_:ArithmeticException){null}catch(_:NumberFormatException){null}
    private fun amount(value:Long)=BigDecimal.valueOf(value,2).stripTrailingZeros().toPlainString()
}

/** Snapshot is ephemeral; implementations must exclude editable/password nodes from text. */
data class UssdScreen(val session: String,val windowId:Int,val text:String,val canReply:Boolean)

interface InteractiveUssdSession {
    suspend fun readiness(job:Assignment):List<ReadinessCheck>
    suspend fun open(job:Assignment,command:String):UssdScreen
    suspend fun current(session:String):UssdScreen
    /** Revalidate the exact prompt inside the implementation before setting text/clicking Send. */
    suspend fun submitPin(job:Assignment,screen:UssdScreen,pin:CharArray):String
    suspend fun closeBeforeSubmission(session:String)
    fun release(session:String)
}

interface ProviderPinSource {
    fun configured():Boolean
    fun read():CharArray
}

/** Inject into WorkerEngine only after the backend and device profile are approved. */
class Evc712Provider(private val session:InteractiveUssdSession,private val pins:ProviderPinSource,
    private val parser:Evc712Parser=Evc712Parser()):ProviderAdapter {
    override val providerId="evc-plus"
    override val flowVersion="evc-712-v1"
    override val submissionBoundary="PIN Send; caller must commit SUBMISSION_POSSIBLE first"
    private var prepared:Pair<String,UssdScreen>?=null
    override suspend fun readiness(job:Assignment)=session.readiness(job)+ReadinessCheck("Provider PIN",pins.configured(),"Local protected credential")

    override suspend fun prepare(job:Assignment) {
        check(prepared==null) {"SESSION_ALREADY_ACTIVE"}
        parser.validate(job)
        val screen=session.open(job,parser.command(job))
        prepared=job.attemptId to screen
        if(!screen.canReply)throw WorkerFailure.Protocol("ReplyFieldUnavailable")
        when(parser.verifyPrompt(job,screen.text)) {
            Evc712Parser.Prompt.MISMATCH -> throw WorkerFailure.Protocol("PromptMismatch")
            Evc712Parser.Prompt.UNRECOGNIZED -> throw WorkerFailure.Protocol("UnrecognizedPrompt")
            else -> Unit
        }
    }

    override suspend fun executeSubmission(job:Assignment):Evidence {
        val saved=prepared?:error("NO_VERIFIED_PROMPT")
        check(saved.first==job.attemptId)
        // Consume the in-memory entry before any reply action: callbacks cannot submit twice.
        prepared=null
        try {
            val fresh=session.current(saved.second.session)
            check(fresh.windowId==saved.second.windowId && fresh.canReply && parser.verifyPrompt(job,fresh.text)==Evc712Parser.Prompt.MATCH) {"PROMPT_CHANGED"}
            val pin=pins.read()
            try {
                require(pin.size in 4..12 && pin.all{it in '0'..'9'}) {"INVALID_LOCAL_PIN"}
                return parser.finalResult(job,session.submitPin(job,fresh,pin))
            } finally {pin.fill('\u0000')}
        } finally {session.release(saved.second.session)}
    }

    override fun interpret(job:Assignment,evidence:Evidence):Evidence {
        if(evidence.kind==ResultKind.UNKNOWN)return evidence
        val code=if(evidence.kind==ResultKind.SUCCESS_CONFIRMED) "EvcSuccess" else "InsufficientBalance"
        return if(evidence.code==code && evidence.payloadHash==job.payloadHash && evidence.amountMinor==job.amountMinor && evidence.currency==job.currency)
            evidence else Evidence(ResultKind.UNKNOWN,"EvidenceMismatch")
    }
    override suspend fun cancelBeforeSubmission(job:Assignment) {
        val saved=prepared;prepared=null
        if(saved!=null)try{session.closeBeforeSubmission(saved.second.session)}finally{session.release(saved.second.session)}
    }
    override suspend fun captureEvidence(job:Assignment):Evidence?=null
    override suspend fun recover(job:Assignment):Evidence?=null
}
