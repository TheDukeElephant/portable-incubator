from app import create_app

app = create_app()

if __name__ == "__main__":
    # Note: Running with debug=True is convenient for development,
    # but should be disabled in a production environment.
    # host='0.0.0.0' makes the server accessible on your network.
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)