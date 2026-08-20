"""Mock CRM. Stands in for the real tools an agent would call."""

_CUSTOMERS = {
    "42": {"customer_id": "42", "name": "Ada Lovelace", "tier": "gold", "note": ""},
    "99": {"customer_id": "99", "name": "Alan Turing", "tier": "silver", "note": ""},
    "17": {"customer_id": "17", "name": "Grace Hopper", "tier": "gold", "note": ""},
    "23": {"customer_id": "23", "name": "Katherine Johnson", "tier": "platinum", "note": ""},
    "31": {"customer_id": "31", "name": "Barbara Liskov", "tier": "silver", "note": ""},
    "58": {"customer_id": "58", "name": "Margaret Hamilton", "tier": "gold", "note": ""},
    "64": {"customer_id": "64", "name": "Radia Perlman", "tier": "bronze", "note": ""},
    "76": {"customer_id": "76", "name": "Shafi Goldwasser", "tier": "silver", "note": ""},
}


class ToolError(Exception):
    pass


def get_customer(customer_id: str, **_):
    record = _CUSTOMERS.get(str(customer_id))
    if record is None:
        raise ToolError(f"no customer {customer_id}")
    return dict(record)


def update_customer(customer_id: str, **fields):
    record = _CUSTOMERS.get(str(customer_id))
    if record is None:
        raise ToolError(f"no customer {customer_id}")
    record.update({k: v for k, v in fields.items() if k in record})
    return dict(record)


def delete_customer(customer_id: str, **_):
    if str(customer_id) not in _CUSTOMERS:
        raise ToolError(f"no customer {customer_id}")
    del _CUSTOMERS[str(customer_id)]
    return {"deleted": customer_id}


REGISTRY = {
    "get_customer": get_customer,
    "update_customer": update_customer,
    "delete_customer": delete_customer,
}

