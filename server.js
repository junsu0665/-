const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const http = require('http');

const app = express();
const port = process.env.PORT || 8443;

// IP 주소 가져오기 함수
function getIPAddress() {
    const interfaces = os.networkInterfaces();
    for (const devName in interfaces) {
        const iface = interfaces[devName];
        for (let i = 0; i < iface.length; i++) {
            const alias = iface[i];
            if (alias.family === 'IPv4' && alias.address !== '127.0.0.1' && !alias.internal) {
                return alias.address;
            }
        }
    }
    return '0.0.0.0';
}

app.use(express.static(path.join(__dirname, 'public')));
app.use(bodyParser.json());

// CORS 설정 추가
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    next();
});

// 로깅 미들웨어 개선
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
    next();
});

const gamesFilePath = path.join(__dirname, 'games.json');

function readGames() {
    try {
        const data = fs.readFileSync(gamesFilePath, 'utf8');
        return JSON.parse(data);
    } catch (err) {
        console.error('Error reading games:', err);
        return [];
    }
}

function writeGames(games) {
    try {
        fs.writeFileSync(gamesFilePath, JSON.stringify(games, null, 2));
    } catch (err) {
        console.error('Error writing games:', err);
    }
}

app.get('/api/games', (req, res) => {
    const games = readGames();
    res.json(games);
});

app.post('/api/games', (req, res) => {
    const games = req.body;
    writeGames(games);
    res.json(games);
});

// 루트 경로 처리 추가
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 에러 핸들링 미들웨어 개선
app.use((err, req, res, next) => {
    console.error('Error:', err.message);
    console.error('Stack:', err.stack);
    res.status(500).send('Internal Server Error');
});

// HTTP 서버 실행
const httpServer = http.createServer(app);
httpServer.listen(port, '0.0.0.0', () => {
    console.log(`HTTP Server running on port ${port}`);
}).on('error', (err) => {
    console.error('Error starting HTTP server:', err);
});

// 서버 상태 확인용 엔드포인트 추가
app.get('/health', (req, res) => {
    res.status(200).send('OK');
});
