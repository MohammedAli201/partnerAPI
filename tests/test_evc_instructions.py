import unittest
from decimal import Decimal
from types import SimpleNamespace

from evc_instructions import transfer_instruction


class EvcInstructionTests(unittest.TestCase):
    def payload(self):
        return SimpleNamespace(provider='EVC', currency='USD', amount=Decimal('50'),
            recipient='+252615738865', request_payload={'beneficiary': {
                'name': 'Shukri abdi ahmed', 'mobile': '+252615738865'}})

    def test_canonical_number_and_name_are_preserved(self):
        payload = self.payload()
        instruction = transfer_instruction(payload)
        self.assertEqual(instruction['command'], '*712*615738865*50#')
        self.assertEqual(instruction['recipient_name'], 'Shukri abdi ahmed')
        self.assertEqual(payload.recipient, '+252615738865')
        self.assertFalse(instruction['payment_executed'])

    def test_conflicting_number_and_missing_name_rejected(self):
        payload = self.payload()
        payload.request_payload['beneficiary']['mobile'] = '+252619882929'
        with self.assertRaises(ValueError):
            transfer_instruction(payload)
        payload = self.payload()
        del payload.request_payload['beneficiary']['name']
        with self.assertRaises(ValueError):
            transfer_instruction(payload)

    def test_foreign_number_and_fractional_cent_rejected(self):
        payload = self.payload()
        payload.recipient = '+47615738865'
        with self.assertRaises(ValueError):
            transfer_instruction(payload)
        payload = self.payload()
        payload.amount = Decimal('1.001')
        with self.assertRaises(ValueError):
            transfer_instruction(payload)
