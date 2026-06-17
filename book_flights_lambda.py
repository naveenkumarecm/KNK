import json


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Flight booked successfully! Your confirmation number is BK-2026-78432. You will receive an email with your booking details shortly."
        })
    }
