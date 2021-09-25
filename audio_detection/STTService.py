import sys
import speech_recognition
import firebase_admin
from firebase_admin import db
from datetime import datetime

# function for submitting help request
def process_text(text, audio, dbRef):
    print("DECODED TEXT: " + text)

    # Look for keyword
    if text.find("send help") != -1:
        print("HELP REQUEST HAS BEEN SENT")

        # Post request in firebase RTDB
        dbRef.push({
            "timestamp": datetime.now().strftime("%d-%b-%Y (%H:%M:%S.%f)"),
            "type": "audio",
            "audioTranscript": text
        })

# Crate listen function
def listen(recognizer, dbRef):
        try:
            with speech_recognition.Microphone() as mic:

                recognizer.adjust_for_ambient_noise(mic, duration=0.2)
                audio = recognizer.listen(mic, phrase_time_limit = 5)

                text = recognizer.recognize_google(audio)
                text = text.lower()

            # Process input text (MIGHT NEED TO RM FOR ASYNC)
            process_text(text, audio, dbRef)

        except speech_recognition.UnknownValueError:
            recognizer = speech_recognition.Recognizer()

# Entry point function
def main():

    # Read userID
    userID = sys.argv[1]

    # Connect to firebase database
    databaseURL = 'https://emergency-monitor-hz21-default-rtdb.europe-west1.firebasedatabase.app'
    cred_obj = firebase_admin.credentials.Certificate('../auth_key/key.json')
    default_app = firebase_admin.initialize_app(cred_obj, {
	   'databaseURL' : databaseURL
	})

    # Create database reference
    ref = db.reference("/users/" + userID + '/emergencies')

    # Set up recognizer
    recognizer = speech_recognition.Recognizer()

    # Start event loop
    while True:
        listen(recognizer, ref)

# Define entry point
if __name__ == "__main__":
    main()
