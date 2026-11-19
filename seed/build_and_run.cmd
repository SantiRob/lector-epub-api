@echo off
cd /d "%~dp0.."
echo inicio %date% %time% > seed\build.log
docker version --format "docker {{.Server.Version}}" >> seed\build.log 2>&1
docker compose -f docker-compose.yml -f docker-compose.seed.yml up -d --build >> seed\build.log 2>&1
echo compose exit=%errorlevel% >> seed\build.log
timeout /t 25 /nobreak > nul
docker compose -f docker-compose.yml -f docker-compose.seed.yml ps >> seed\build.log 2>&1
docker compose -f docker-compose.yml -f docker-compose.seed.yml logs api >> seed\build.log 2>&1
curl.exe -s http://127.0.0.1:8000/api/v1/health >> seed\build.log 2>&1
echo. >> seed\build.log
curl.exe -s "http://127.0.0.1:8000/api/v1/books?limit=50" > seed\books.json 2>> seed\build.log
echo FIN >> seed\build.log
exit
