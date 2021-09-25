import speech_recognition
import firebase_admin
from firebase_admin import db
from firebase_admin import storage
from datetime import datetime

# function for submitting help request
def process_text(text, audio, dbRef, bucket, uid):
    print("DECODED TEXT: " + text)

    # Look for keyword
    if text.find("send help") != -1:
        print("HELP REQUEST HAS BEEN SENT")

        # Save audio file
        with open("audio_file.wav", "wb") as file:
            file.write(audio.get_wav_data())

        blobName = datetime.now().strftime("AUDIO%d%b%Y%H%M%S") + '.wav'
        blobPath = str(uid) + '/' + blobName
        blob = bucket.blob(blobPath)
        blob.upload_from_filename('audio_file.wav')

        # Post request in firebase RTDB
        dbRef.push({
            "timestamp": datetime.now().strftime("%d-%b-%Y (%H:%M:%S.%f)"),
            "type": "audio",
            "resourceBucketLocation" : blobPath,
            "audioTranscript": text
        })

# Crate listen function
def listen(recognizer, dbRef, bucket, uid):
        try:
            with speech_recognition.Microphone() as mic:

                recognizer.adjust_for_ambient_noise(mic, duration=0.2)
                audio = recognizer.listen(mic, phrase_time_limit = 5)

                text = recognizer.recognize_google(audio)
                text = text.lower()

            # Process input text (MIGHT NEED TO RM FOR ASYNC)
            process_text(text, audio, dbRef, bucket, uid)

        except speech_recognition.UnknownValueError:
            recognizer = speech_recognition.Recognizer()

# Entry point function
def main():

    # Read userID
    with open('../auth_key/user_id.txt') as f:
        userID = f.readlines()[0]

    print(userID)

    # Connect to firebase database
    databaseURL = 'https://emergency-monitor-hz21-default-rtdb.europe-west1.firebasedatabase.app'
    bucketURL = 'emergency-monitor-hz21.appspot.com'

    cred_obj = firebase_admin.credentials.Certificate('../auth_key/key.json')
    default_app = firebase_admin.initialize_app(cred_obj, {
	   'databaseURL' : databaseURL,
       'storageBucket' : bucketURL
	})

    # Create database reference and storage bucket
    ref = db.reference("/users/" + userID + '/emergencies')
    bucket = storage.bucket()

    # Set up recognizer
    recognizer = speech_recognition.Recognizer()

    # Start event loop
    while True:
        listen(recognizer, ref, bucket, userID)

# Define entry point
if __name__ == "__main__":
    main()
