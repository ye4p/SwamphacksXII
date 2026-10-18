import os
from flask import Flask, send_from_directory, jsonify, make_response

app = Flask(__name__, static_folder='static')

# 1. Serve the initial HTML page
@app.route("/")
def index():
    return send_from_directory('static/src', 'index.html')

# 2. Serve static files, forcing application/javascript for .jsx files
@app.route("/static/src/<path:filename>")
def serve_static(filename):
    file_path = os.path.join(app.static_folder, 'src', filename)
    
    # Explicitly force JavaScript mimetype for .jsx files
    if filename.endswith('.jsx'):
        return send_from_directory('static/src', filename, mimetype='application/javascript')
        
    return send_from_directory('static/src', filename)

# 3. Your team's API endpoint
@app.route("/api/v1/hello")
def get_hello():
    return jsonify({
        "message": "Hello from the Python backend API!",
        "status": "success"
    })

# 4. Prevent the 404 favicon error
@app.route("/favicon.ico")
def favicon():
    return make_response("", 204)

if __name__ == "__main__":
    app.run(debug=True, port=8000)