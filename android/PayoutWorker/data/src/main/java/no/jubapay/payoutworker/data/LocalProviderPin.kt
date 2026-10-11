package no.jubapay.payoutworker.data

import no.jubapay.payoutworker.domain.ProviderPinSource

/** Explicit local provisioning only. Never place this credential in a worker payload or log. */
class LocalProviderPin(private val vault:Vault):ProviderPinSource {
    override fun configured()=vault.get("evc-provider-pin")!=null
    fun set(pin:CharArray,confirmation:CharArray) {
        try {
            require(pin.size in 4..12 && pin.all{it in '0'..'9'} && pin.contentEquals(confirmation))
            vault.put("evc-provider-pin",String(pin))
            vault.remove("evc-pin-subscription")
        } finally {pin.fill('\u0000');confirmation.fill('\u0000')}
    }
    override fun read()=(vault.get("evc-provider-pin")?:error("PROVIDER_PIN_NOT_CONFIGURED")).toCharArray()
    fun bindToSubscription(subscription:Int) {
        val bound=vault.get("evc-pin-subscription")?.toInt()
        check(bound==null||bound==subscription){"EVC_PIN_SIM_CHANGED"}
        if(bound==null)vault.put("evc-pin-subscription",subscription.toString())
    }
}
