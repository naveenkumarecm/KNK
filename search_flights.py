import json

with open("flight-data.json") as f:
    FLIGHTS = json.load(f)

NO_INFO = {"statusCode": 200, "body": json.dumps({"message": "There is no information available for the requested route."})}


def lambda_handler(event, context):
    body = event if "origin" in event else json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event.get("body", {})

    origin = body.get("origin", "").strip()
    destination = body.get("destination", "").strip()
    seat_class = body.get("seat_class", "").strip().lower()

    if not origin:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing required parameter: origin"})}

    def matches(field, query):
        return query.upper() in field.upper()

    results = [f for f in FLIGHTS if matches(f["origin"], origin)]
    if destination:
        results = [f for f in results if matches(f["destination"], destination)]

    if not results:
        return NO_INFO

    if seat_class:
        results = [f for f in results if seat_class in f["seat_class_available"]]
        if not results:
            return NO_INFO

    return {"statusCode": 200, "body": json.dumps({"flights": results, "total_results": len(results)})}
