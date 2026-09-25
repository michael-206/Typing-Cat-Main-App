# Typing-Cat-Main-App

Project Contents
----------------
typing_cat_main_game/
├─ my-flask-app.tar        <-- Docker image of the Flask app
├─ instance/
│   └─ app.db              <-- Pre-populated SQLite database (DO NOT DELETE)
├─ docker-compose.yml      <-- Optional: simplifies container deployment
└─ README.txt              <-- This instructions file

Important Notes
---------------
1. The database (app.db) contains pre-made entries, including the admin account.
2. The database is stored outside the container as a "volume". This ensures that:
   - Updating or replacing the Docker container will NOT erase the DB.
   - All existing entries remain intact.
3. The container is stateless; the code can be updated by sending a new Docker image.

How to Deploy (IT Department)
-----------------------------
Step 1: Load the Docker image
  1. Copy `typing_cat_main_app.tar` to the server.
  2. Run:
     docker load -i my-flask-app.tar

Step 2: Prepare the database folder
  1. Choose a permanent path for the database on the server, e.g.:
       /srv/myapp/instance
  2. Copy the `instance/app.db` from this package to that folder.

Step 3: Run the Flask container
  1. Use Docker to start the container with the database mounted:
     docker run -d -p 5000:5000 \
       -v /srv/myapp/instance:/app/instance \
       typing_cat_main_app:v1
  2. The Flask app will now be accessible on port 5000.

Optional: Using Docker Compose
------------------------------
1. Copy the package to the server.
2. Edit `docker-compose.yml` if needed (ports or paths).
3. Run:
   docker-compose up -d --build
4. This method automatically mounts the database and runs the container.

Updating the App with a New Version
-----------------------------------
1. Build and save a new Docker image (on your laptop):
   docker build -t typing_cat_main_app:v2 .
   docker save -o typing_cat_main_app-v2.tar typing_cat_main_app:v2

2. Send the new image (`typing_cat_main_app-v2.tar`) to IT.

3. IT loads the new image:
   docker load -i typing_cat_main_app-v2.tar

4. Stop the old container:
   docker stop <old_container_id>

5. Run the new container with the **same database volume**:
   docker run -d -p 5000:5000 \
     -v /srv/myapp/instance:/app/instance \
     typing_cat_main_app:v2

✅ Database remains intact. Pre-made entries are preserved.

Best Practices
--------------
- NEVER copy the DB into the Docker image.
- Always mount the database as a volume.
- Backup the DB before making major updates (optional, but recommended).