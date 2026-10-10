"""Server-enrolled synthetic fixtures for API security-boundary regressions."""
from agents.utility_based.execution_assistance.review_context import review_registry


def enroll(client, extraction, corrections=None):
    response = client.post("/api/documents/aadhaar/confirm", json={"confirmed": True,
        "extraction": extraction.model_dump(mode="json"), "corrections": corrections or {}})
    assert response.status_code == 200
    body = response.json()
    reference = body["confirmed_context"]["review_context"]
    secret = body.pop("review_capability")
    headers = {"Authorization": "Bearer " + secret, "X-Review-Context": reference["id"]}
    return body, headers


def resolve_review(client, body, headers):
    base = "/api/review-contexts/" + body["confirmed_context"]["review_context"]["id"]
    response = client.post(base + "/resolve", headers=headers)
    assert response.status_code == 200, response.text
    response = client.get(base + "/review", headers=headers)
    assert response.status_code == 200, response.text
    return response


def confirm_review(client, reviewed, headers):
    body = reviewed.json()
    base = "/api/review-contexts/" + body["confirmed_context"]["review_context"]["id"]
    return client.post(base + "/action", headers=headers, json={"action": "confirm_post_office",
        "confirm_resolver_projection": True, "review_reference": body["review_reference"]})


def bind_context(context, *, projected=False, active=False):
    result = context.address_resolution
    canonical = context.model_copy(deep=True, update={"review_context": None})
    canonical.facts.pop("address_resolution", None)
    canonical.facts = {k: f for k, f in canonical.facts.items() if f.resolution_projection is None}
    context_id, secret, bound = review_registry.create(canonical)
    if result is not None:
        reservation, _ = review_registry.begin_lookup(context_id)
        review_registry.finish_lookup(context_id, reservation, result)
        reference, bound = review_registry.publish(context_id)
        if projected:
            bound = review_registry.confirm(context_id, reference, "confirm_post_office")
    if active:
        review_registry.reserve_launch(bound)
        review_registry.finish_launch(context_id, True)
    return bound, {"Authorization": "Bearer " + secret, "X-Review-Context": context_id}
