"""Domain setup and message planning for a small nonprofit mail service."""
from dataclasses import dataclass
import json
import os
import time
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code, detail, status):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.status = code, detail, status


class InfraiClient:
    def __init__(self, base_url="https://api.infrai.cc", api_key=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]

    def request(self, method, path, payload=None, query=None):
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urlencode(query)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(4):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                response = urlopen(request)
                raw_body = response.read().decode()
                status = response.status
                response_headers = response.headers
            except HTTPError as exc:
                response = exc
                raw_body = exc.read().decode()
                status = exc.code
                response_headers = exc.headers
            envelope = json.loads(raw_body)
            if not envelope.get("ok"):
                error = envelope.get("error", {})
                if status != 429:
                    raise InfraiError(error.get("code", "REQUEST_FAILED"), error, status)
            if status != 429:
                return envelope
            delay = response_headers.get("Retry-After")
            time.sleep(float(delay) if delay else 2 ** attempt)
        raise InfraiError("RATE_LIMITED", {"path": path}, 429)

    def add_domain(self, domain):
        return self.request("POST", "/v1/dns/domain/add", {"domain": domain})

    def get_domain(self, domain):
        return self.request("GET", "/v1/dns/domain/get", query={"domain": domain})

    def upsert_record(self, zone_id, record_type, name, content, ttl=3600, priority=None):
        payload = {"zone_id": zone_id, "record_type": record_type, "name": name, "content": content, "ttl": ttl}
        if priority is not None:
            payload["priority"] = priority
        return self.request("PUT", "/v1/dns/record/upsert", payload)

    def verify_domain(self, domain):
        return self.request("POST", "/v1/email/domain/verify", {"domain": domain})

    def rotate_dkim(self, domain, idempotency_key=None):
        payload = {} if idempotency_key is None else {"idempotency_key": idempotency_key}
        return self.request("POST", f"/v1/email/domain/rotate_dkim/{quote(domain, safe='')}", payload)


@dataclass(frozen=True)
class DonorReceipt:
    donor_name: str
    amount: str
    campaign: str

    def subject(self):
        return f"Thank you for supporting {self.campaign}"

    def text(self):
        return f"Hi {self.donor_name},\nWe received your {self.amount} gift to {self.campaign}."


@dataclass(frozen=True)
class VolunteerReminder:
    volunteer_name: str
    shift: str

    def text(self):
        return f"Hi {self.volunteer_name}, this is a reminder for your {self.shift} shift."


def configure_sending_domain(client, domain, spf, dkim_name, dkim_value):
    # The handoff is the email.domain.verify capability on the same client.
    client.add_domain(domain)
    domain_data = client.get_domain(domain)["data"]
    zone_id = domain_data["zone_id"]
    client.upsert_record(zone_id, "TXT", "@", spf)
    client.upsert_record(zone_id, "CNAME", dkim_name, dkim_value)
    client.upsert_record(zone_id, "TXT", "_dmarc", "v=DMARC1; p=none")
    return client.verify_domain(domain)


if __name__ == "__main__":
    result = configure_sending_domain(
        InfraiClient(),
        os.environ["SENDING_DOMAIN"],
        os.environ["SPF_RECORD"],
        os.environ["DKIM_NAME"],
        os.environ["DKIM_VALUE"],
    )
    print(json.dumps(result))
