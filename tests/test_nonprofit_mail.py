from src.nonprofit_mail import DonorReceipt, VolunteerReminder


def test_receipt_and_reminder_are_domain_messages():
    receipt = DonorReceipt("Mina", "$40", "Food drive")
    reminder = VolunteerReminder("Kai", "Saturday morning")
    assert receipt.subject() == "Thank you for supporting Food drive"
    assert "$40" in receipt.text()
    assert reminder.text().endswith("Saturday morning shift.")


def test_cli_configures_domain(monkeypatch, capsys):
    import runpy
    from unittest.mock import patch

    values = {
        'INFRAI_API_KEY': 'test-key', 'SENDING_DOMAIN': 'mail.example.org',
        'SPF_RECORD': 'v=spf1 -all', 'DKIM_NAME': 'test._domainkey',
        'DKIM_VALUE': 'dkim.example.org',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with patch('urllib.request.urlopen') as transport:
        import json
        transport.return_value.read.side_effect = [
            json.dumps(result).encode() for result in [
                {'ok': True}, {'ok': True, 'data': {'zone_id': 'zone-test'}},
                {'ok': True}, {'ok': True}, {'ok': True}, {'ok': True},
            ]
        ]
        runpy.run_module('src.nonprofit_mail', run_name='__main__')
        requests = [call.args[0] for call in transport.call_args_list]
    assert [req.method for req in requests] == ['POST', 'GET', 'PUT', 'PUT', 'PUT', 'POST']
    assert json.loads(requests[2].data)['zone_id'] == 'zone-test'
    assert json.loads(requests[-1].data) == {'domain': values['SENDING_DOMAIN']}
    assert json.loads(capsys.readouterr().out)['ok'] is True


def test_rotation_uses_only_contract_fields():
    from unittest.mock import Mock
    from src.nonprofit_mail import InfraiClient

    client = InfraiClient(api_key='test-key')
    client.request = Mock()
    client.rotate_dkim('mail.example.org')
    client.request.assert_called_with('POST', '/v1/email/domain/rotate_dkim/mail.example.org', {})
    client.rotate_dkim('mail.example.org', idempotency_key='rotation-test')
    client.request.assert_called_with(
        'POST', '/v1/email/domain/rotate_dkim/mail.example.org', {'idempotency_key': 'rotation-test'}
    )
    client.rotate_dkim('mail.example.org/other')
    client.request.assert_called_with('POST', '/v1/email/domain/rotate_dkim/mail.example.org%2Fother', {})
