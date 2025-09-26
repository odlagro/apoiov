# Certifique-se que no final do seu app.py está assim:

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5001))  # Render define PORT
    app.run(host="0.0.0.0", port=port, debug=False)
