package no.jubapay.payoutworker.data

import no.jubapay.payoutworker.domain.ProviderPinSource

/** Explicit local provisioning only. Never place this credential in a worker payload or log. */
class LocalProviderPin(private val vault:Vault):ProviderPinSource {
    override fun configured()=vault.get("evc-provider-pin")!=null
    fun set(pin:CharArray,confirmation:CharArray) {
        try {
            require(pin.size in 4..12 && pin.all{it in '0'..'9'} && pin.contentEquals(confirmation))
            vault.put("evc-provider-pin",String(pin))
        } finally {pin.fill('\u0000');confirmation.fill('\u0000')}
    }
    override fun read()=(vault.get("evc-provider-pin")?:error("PROVIDER_PIN_NOT_CONFIGURED")).toCharArray()
}
