from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Dict, List
import json
import uuid

app = FastAPI()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.usernames: Dict[str, str] = {}
        self.user_ids: Dict[str, str] = {}  # username -> user_id mapping

    async def connect(self, websocket: WebSocket, user_id: str, username: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.usernames[user_id] = username
        self.user_ids[username] = user_id

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            username = self.usernames.get(user_id)
            if username in self.user_ids:
                del self.user_ids[username]
            del self.active_connections[user_id]
            del self.usernames[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast(self, message: str):
        for user_id, connection in self.active_connections.items():
            await connection.send_text(message)

    async def send_to_user(self, message: str, from_user_id: str, to_username: str):
        from_username = self.usernames.get(from_user_id, "Unknown")

        # Find user_id by username
        to_user_id = self.user_ids.get(to_username)

        if to_user_id and to_user_id in self.active_connections:
            # Send to recipient
            private_msg = f"[ЛИЧНО от {from_username}]: {message}"
            await self.active_connections[to_user_id].send_text(private_msg)

            # Send confirmation to sender
            confirm_msg = f"[Вы отправили {to_username}]: {message}"
            await self.send_personal_message(confirm_msg, from_user_id)
        else:
            # User not found
            error_msg = f"Пользователь '{to_username}' не найден или offline"
            await self.send_personal_message(error_msg, from_user_id)

    def get_online_users(self):
        return {user_id: self.usernames[user_id] for user_id in self.active_connections.keys()}

    async def send_user_list(self):
        user_list = [
            {"username": username, "user_id": user_id}
            for user_id, username in self.usernames.items()
        ]
        user_list_msg = {
            "type": "user_list",
            "users": user_list
        }
        await self.broadcast(json.dumps(user_list_msg))


manager = ConnectionManager()

# HTML страница
html = """
<!DOCTYPE html>
<html>
    <head>
        <title>WebSocket Chat с личными сообщениями</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { display: flex; gap: 20px; }
            .chat-area { flex: 2; }
            .users-area { flex: 1; border-left: 1px solid #ccc; padding-left: 20px; }
            #messages { list-style: none; padding: 0; height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
            .message { margin: 5px 0; padding: 5px; border-radius: 5px; }
            .private { background-color: #ffe6e6; border-left: 3px solid #ff0000; }
            .system { background-color: #f0f0f0; color: #666; }
            .user-list { list-style: none; padding: 0; }
            .user-item { padding: 8px; margin: 5px; background: #f0f8ff; border-radius: 5px; cursor: pointer; }
            .user-item:hover { background: #e0f0ff; }
            .user-item.selected { background: #b3d9ff; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>WebSocket Chat с личными сообщениями</h1>
        <div class="container">
            <div class="chat-area">
                <div>Ваш username: <span id="myUsername"></span></div>

                <form action="" onsubmit="sendMessage(event)">
                    <input type="text" id="messageText" autocomplete="off" placeholder="Введите сообщение для всех..."/>
                    <button type="submit">Отправить всем</button>
                </form>

                <form action="" onsubmit="sendPrivateMessage(event)">
                    <input type="text" id="privateMessageText" autocomplete="off" placeholder="Личное сообщение..."/>
                    <button type="submit">Отправить лично</button>
                </form>

                <h3>Сообщения:</h3>
                <ul id='messages'></ul>
            </div>

            <div class="users-area">
                <h3>Онлайн пользователи (кликните для выбора):</h3>
                <ul id='userList' class='user-list'></ul>
            </div>
        </div>

        <script>
            let userId = null;
            let username = null;
            let ws = null;
            let selectedUser = null;

            // Инициализация при загрузке страницы
            window.onload = function() {
                username = prompt("Введите ваше имя:") || "User_" + Math.random().toString(36).substr(2, 5);
                userId = Math.random().toString(36).substr(2, 9);
                document.getElementById('myUsername').textContent = username;

                // Установка соединения с сервером
                ws = new WebSocket("ws://localhost:8000/ws/" + userId + "/" + encodeURIComponent(username));

                // Обработчик входящих сообщений от сервера
                ws.onmessage = function(event) {
                    const data = event.data;

                    // Пытаемся распарсить JSON (список пользователей)
                    try {
                        const message = JSON.parse(data);
                        if (message.type === 'user_list') {
                            updateUserList(message.users);
                            return;
                        }
                    } catch (e) {
                        // Это не JSON, обрабатываем как обычное сообщение
                    }

                    // Отображаем обычное сообщение
                    const messages = document.getElementById('messages');
                    const messageElement = document.createElement('li');

                    if (data.includes('[ЛИЧНО') || data.includes('[Вы отправили')) {
                        messageElement.className = 'message private';
                    } else if (data.includes('подключился') || data.includes('отключился')) {
                        messageElement.className = 'message system';
                    } else {
                        messageElement.className = 'message';
                    }

                    const content = document.createTextNode(data);
                    messageElement.appendChild(content);
                    messages.appendChild(messageElement);
                    messages.scrollTop = messages.scrollHeight;
                };

                ws.onclose = function() {
                    console.log("Connection closed");
                };
            };

            // Функция для отправки сообщения всем
            function sendMessage(event) {
                event.preventDefault();
                const input = document.getElementById("messageText");
                if (ws && input.value) {
                    ws.send("ALL:" + input.value);
                    input.value = '';
                }
            }

            // Функция для отправки личного сообщения
            function sendPrivateMessage(event) {
                event.preventDefault();
                const input = document.getElementById("privateMessageText");

                if (!selectedUser) {
                    alert("Сначала выберите пользователя из списка справа!");
                    return;
                }

                if (ws && input.value && selectedUser) {
                    ws.send("PRIVATE:" + selectedUser + ":" + input.value);
                    input.value = '';
                }
            }

            // Функция для обновления списка пользователей
            function updateUserList(users) {
                const userList = document.getElementById('userList');
                userList.innerHTML = '';

                users.forEach(user => {
                    // Пропускаем себя
                    if (user.user_id === userId) return;

                    const userItem = document.createElement('li');
                    userItem.className = 'user-item';
                    userItem.textContent = user.username;
                    userItem.dataset.username = user.username;

                    // Выделяем выбранного пользователя
                    if (selectedUser === user.username) {
                        userItem.classList.add('selected');
                    }

                    // Обработчик клика для выбора пользователя
                    userItem.onclick = function() {
                        // Снимаем выделение со всех
                        document.querySelectorAll('.user-item').forEach(item => {
                            item.classList.remove('selected');
                        });

                        // Выделяем текущего
                        this.classList.add('selected');
                        selectedUser = this.dataset.username;

                        // Обновляем placeholder
                        document.getElementById('privateMessageText').placeholder = 
                            `Личное сообщение для ${selectedUser}...`;
                    };

                    userList.appendChild(userItem);
                });

                // Добавляем заглушку, если пользователей нет
                if (userList.children.length === 0) {
                    const noUsers = document.createElement('li');
                    noUsers.textContent = 'Нет других пользователей онлайн';
                    noUsers.style.color = '#666';
                    userList.appendChild(noUsers);
                }
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws/{user_id}/{username}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, username: str):
    # Подключаем нового клиента
    await manager.connect(websocket, user_id, username)

    # Отправляем текущий список пользователей всем
    await manager.send_user_list()

    try:
        # Оповещаем всех о новом пользователе
        await manager.broadcast(f"Пользователь {username} подключился к чату!")

        while True:
            # Ждем сообщение от клиента
            data = await websocket.receive_text()

            # Обрабатываем разные типы сообщений
            if data.startswith("ALL:"):
                # Сообщение для всех
                message = data[4:]
                await manager.broadcast(f"{username}: {message}")

            elif data.startswith("PRIVATE:"):
                # Личное сообщение
                parts = data.split(":", 2)
                if len(parts) >= 3:
                    to_username = parts[1]
                    private_message = parts[2]
                    await manager.send_to_user(private_message, user_id, to_username)

    except WebSocketDisconnect:
        # Если клиент отключился
        manager.disconnect(user_id)
        await manager.broadcast(f"Пользователь {username} отключился.")
        await manager.send_user_list()