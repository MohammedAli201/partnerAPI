package no.jubapay.payoutworker.domain

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class Evc712Test {
    private fun job(amount:Long=100):Assignment {
        val a=Assignment("payout","attempt","device",1,"evc-plus","account",1,"615738865","MSISDN",amount,"USD","","evc-712-v1",100000,100000,"correlation")
        return a.copy(payloadHash=a.immutableHash())
    }
    private fun prompt(number:String="615738865",amount:String="1")="Uwareeji $$amount EXAMPLE RECIPIENT ($number), Fadlan..Geli..PIN-kaaga"
    private val parser=Evc712Parser()
    private val config=DeviceConfig("device","evc-plus","account",1,false)
    private class Pins:ProviderPinSource {
        var reads=0;var last:CharArray?=null
        override fun configured()=true
        override fun read():CharArray {reads++;return charArrayOf('1','2','3','4').also{last=it}}
    }
    private inner class Session(val store:PaymentSafetyTest.Store):InteractiveUssdSession {
        var opens=0;var sends=0;var cancellations=0;var lost=false;var changed=false
        var text=prompt();var response="Haraaga xisaabtaadu kuguma filna"
        override suspend fun readiness(job:Assignment)=emptyList<ReadinessCheck>()
        override suspend fun open(job:Assignment,command:String):UssdScreen {
            assertEquals(Phase.PREPARING,store.a!!.phase);assertEquals("*712*615738865*1#",command);opens++
            return UssdScreen("session",7,text,true)
        }
        override suspend fun current(session:String)=UssdScreen(session,7,if(changed)prompt("615738866") else text,true)
        override suspend fun submitPin(job:Assignment,screen:UssdScreen,pin:CharArray):String {
            assertNotNull(store.a!!.submissionAt);assertNotNull(store.a!!.authorizationId)
            assertEquals(Phase.AWAITING_CONFIRMATION,store.a!!.phase);sends++
            if(lost)throw IllegalStateException("Injected dialogue loss")
            return response
        }
        override suspend fun closeBeforeSubmission(session:String){cancellations++}
        override fun release(session:String){}
    }
    private fun engine(s:PaymentSafetyTest.Store,p:Evc712Provider,b:PaymentSafetyTest.Server=PaymentSafetyTest.Server(job()))=
        WorkerEngine(s,b,p,Readiness{emptyList()},{config},TimeSource{1000})

    @Test fun commandUsesIntegerMinorUnitsWithoutRounding() {
        assertEquals("*712*615738865*1#",parser.command(job()))
        assertEquals("*712*615738865*1.25#",parser.command(job(125)))
        assertEquals("*712*615738865*0.01#",parser.command(job(1)))
    }
    @Test fun promptMustMatchRecipientAndAmountExactly() {
        assertEquals(Evc712Parser.Prompt.MATCH,parser.verifyPrompt(job(),prompt()))
        assertEquals(Evc712Parser.Prompt.MATCH,parser.verifyPrompt(job(),prompt(amount="1.00")))
        assertEquals(Evc712Parser.Prompt.MISMATCH,parser.verifyPrompt(job(),prompt("615738866")))
        assertEquals(Evc712Parser.Prompt.MISMATCH,parser.verifyPrompt(job(),prompt(amount="10")))
        assertEquals(Evc712Parser.Prompt.UNRECOGNIZED,parser.verifyPrompt(job(),prompt(amount="1.001")))
    }
    @Test fun unknownMenuAndCurrencyNeverMatch() {
        assertEquals(Evc712Parser.Prompt.UNRECOGNIZED,parser.verifyPrompt(job(),"Enter PIN"))
        assertEquals(Evc712Parser.Prompt.UNRECOGNIZED,parser.verifyPrompt(job(),prompt().replace('$','€')))
        assertEquals(Evc712Parser.Prompt.UNRECOGNIZED,parser.verifyPrompt(job(),"x".repeat(4097)))
    }
    @Test fun noRealSuccessFormatIsInvented() {
        assertEquals(ResultKind.UNKNOWN,parser.finalResult(job(),"Payment successful").kind)
        assertEquals(ResultKind.NOT_PAID_CONFIRMED,parser.finalResult(job(),"Haraaga xisaabtaadu kuguma filna").kind)
        assertEquals(ResultKind.UNKNOWN,parser.finalResult(job(),"Haraaga xisaabtaadu kuguma filna but another transfer succeeded").kind)
    }
    @Test fun syntheticSuccessTemplateMustBindMoneyAndRecipient() {
        // Artificial grammar ONLY for parser tests, not a claimed operator response.
        val p=Evc712Parser(listOf("TEST {amount} USD to {recipient} REF {reference}"))
        val result=p.finalResult(job(),"TEST 1 USD to 615738865 REF abc-123")
        assertEquals(ResultKind.SUCCESS_CONFIRMED,result.kind);assertEquals("abc-123",result.reference)
        assertEquals(ResultKind.UNKNOWN,p.finalResult(job(),"TEST 2 USD to 615738865 REF abc-123").kind)
        val noRef=Evc712Parser(listOf("TEST {amount} USD to {recipient}"))
        assertNull(noRef.finalResult(job(),"TEST 1 USD to 615738865").reference)
    }
    @Test fun insufficientBalanceIsNotPaidAndDuplicateNeverSubmitsAgain()=runBlocking {
        val s=PaymentSafetyTest.Store();val transport=Session(s);val pins=Pins()
        val e=engine(s,Evc712Provider(transport,pins));e.start();e.cycle();e.cycle()
        assertEquals(1,transport.opens);assertEquals(1,transport.sends)
        assertEquals(Phase.CONFIRMED_NOT_PAID,s.a!!.phase);assertEquals("InsufficientBalance",s.a!!.evidence!!.code)
        assertTrue(pins.last!!.all{it=='\u0000'})
    }
    @Test fun mismatchedPromptNeverReadsOrSendsPin()=runBlocking {
        val s=PaymentSafetyTest.Store();val transport=Session(s).apply{text=prompt("615738866")};val pins=Pins()
        val e=engine(s,Evc712Provider(transport,pins));e.start();e.cycle()
        assertEquals(0,pins.reads);assertEquals(0,transport.sends);assertEquals(1,transport.cancellations)
    }
    @Test fun changedPromptAfterAuthorizationStillCannotSubmit()=runBlocking {
        val s=PaymentSafetyTest.Store();val transport=Session(s).apply{changed=true};val pins=Pins()
        val e=engine(s,Evc712Provider(transport,pins));e.start();e.cycle()
        assertEquals(0,pins.reads);assertEquals(0,transport.sends);assertEquals(Phase.UNKNOWN,s.a!!.phase)
    }
    @Test fun storageFailureBeforePinPreventsPinReadAndSubmission()=runBlocking {
        val s=PaymentSafetyTest.Store().apply{failBoundary=true};val transport=Session(s);val pins=Pins()
        val e=engine(s,Evc712Provider(transport,pins));e.start();e.cycle()
        assertEquals(0,pins.reads);assertEquals(0,transport.sends)
    }
    @Test fun lostDialogueAfterPinIsUnknownNeverReplayed()=runBlocking {
        val s=PaymentSafetyTest.Store();val transport=Session(s).apply{lost=true};val pins=Pins()
        val e=engine(s,Evc712Provider(transport,pins));e.start();e.cycle();e.recover();e.cycle()
        assertEquals(1,transport.sends);assertEquals(Phase.RECONCILIATION_REQUIRED,s.a!!.phase);assertNotNull(s.q)
    }
    @Test fun unrecognizedFinalResponseNeverBecomesSuccess()=runBlocking {
        val s=PaymentSafetyTest.Store();val transport=Session(s).apply{response="New operator response"}
        val e=engine(s,Evc712Provider(transport,Pins()));e.start();e.cycle()
        assertEquals(Phase.UNKNOWN,s.a!!.phase);assertNotNull(s.q)
    }
}
