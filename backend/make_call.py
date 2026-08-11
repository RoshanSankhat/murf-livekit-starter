import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv(".env.local")
load_dotenv(".env")

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
my_number = os.getenv("MY_PHONE_NUMBER")

# Replace with your real TwiML Bin URL from Twilio Console
twiml_url = "https://handler.twilio.com/twiml/EH..."

if not account_sid or not auth_token:
    print("Error: Missing Twilio credentials!")
    exit(1)

client = Client(account_sid, auth_token)

print(f"Initiating call to {my_number}...")

call = client.calls.create(
    url=twiml_url,
    to=my_number,
    from_=my_number
)

print(f"Call successfully queued! Call SID: {call.sid}")
