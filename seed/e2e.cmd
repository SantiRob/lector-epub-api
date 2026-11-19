@echo off
cd /d "%~dp0"
set B=http://127.0.0.1:8000/api/v1
set C=docker compose -f ..\docker-compose.yml -f ..\docker-compose.seed.yml
echo inicio %date% %time% > e2e.log
curl.exe -s -o nul -w "detalle17 %%{http_code}\n" %B%/books/17 >> e2e.log
curl.exe -s -o nul -w "buscar_potter %%{http_code}\n" "%B%/books?q=potter" >> e2e.log
curl.exe -s "%B%/books?q=potter" > e2e_search.json
curl.exe -s -o cover1.img -w "cover1 %%{http_code} %%{content_type} %%{size_download}\n" %B%/books/1/cover >> e2e.log
curl.exe -s -o dl17.epub -w "download17 %%{http_code} %%{content_type} %%{size_download}\n" %B%/books/17/download >> e2e.log
curl.exe -s -o nul -w "noexiste %%{http_code}\n" %B%/books/999/download >> e2e.log
echo {"client_review_id":"3f1c2a9e-8b7d-4e6f-9a1b-2c3d4e5f6a7b","display_name":"Tester","rating":5,"comment":"Prueba e2e"} > review.json
curl.exe -s -w " review1 %%{http_code}\n" -H "Content-Type: application/json" --data-binary @review.json %B%/books/17/reviews >> e2e.log
curl.exe -s -w " review2_mismo_id %%{http_code}\n" -H "Content-Type: application/json" --data-binary @review.json %B%/books/17/reviews >> e2e.log
curl.exe -s -w " lista_reviews %%{http_code}\n" %B%/books/17/reviews >> e2e.log
curl.exe -s -w " libro17 %%{http_code}\n" %B%/books/17 >> e2e.log
%C% restart api >> e2e.log 2>&1
timeout /t 20 /nobreak > nul
%C% logs --tail 8 api >> e2e.log 2>&1
echo FIN >> e2e.log
exit
