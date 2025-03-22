from flask import Flask, request, jsonify, g, render_template
from database import Database

app = Flask(__name__)
db = Database()

# Create tables within the application context
with app.app_context():
    db.create_tables()  # Ensure the tables are created when the app starts

@app.teardown_appcontext
def close_db(exception):
    db.close()

print("Starting Flask server...")

# Route for the homepage
@app.route('/')
def home():
    with app.app_context():
        data = db.fetch_all_data()  # Fetch all data from the database
        print("Fetched data:", data)  # Debugging line to check fetched data
    return render_template('index.html', data=data)  # Render the template with the data

# Endpoint to receive sniffed packets
@app.route('/api/packets', methods=['POST'])
def receive_packets():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Extract relevant data from the request
    mac_address = data.get('mac_address')
    ssid = data.get('ssid')
    signal_strength = data.get('signal_strength')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    client_number = data.get('client_number')
    password = data.get('password')
    security_types = data.get('security_types', [])  # Expecting a list of security types
    is_wps = data.get('is_wps', 0)  # Extract is_wps, default to 0 if not provided

    # Insert data into the database
    db.insert_data(mac_address, ssid, signal_strength, latitude, longitude, client_number, password, security_types, is_wps)

    print("Received packets:", data)
    return jsonify({'message': 'Packets received successfully'}), 200

# Endpoint to receive other data
@app.route('/api/data', methods=['POST'])
def receive_data():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    print("Received data:", data)
    return jsonify({'message': 'Data received successfully'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
