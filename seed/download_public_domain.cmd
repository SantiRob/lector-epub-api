@echo off
cd /d "%~dp0"
if not exist pd mkdir pd
echo inicio %date% %time% > pd.log
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg2000.epub https://gutenberg.pglaf.org/cache/epub/2000/pg2000-images-3.epub >> pd.log 2>&1
echo pg2000 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg320.epub https://gutenberg.pglaf.org/cache/epub/320/pg320-images-3.epub >> pd.log 2>&1
echo pg320 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg49836.epub https://gutenberg.pglaf.org/cache/epub/49836/pg49836-images-3.epub >> pd.log 2>&1
echo pg49836 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg17340.epub https://gutenberg.pglaf.org/cache/epub/17340/pg17340-images-3.epub >> pd.log 2>&1
echo pg17340 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg17073.epub https://gutenberg.pglaf.org/cache/epub/17073/pg17073-images-3.epub >> pd.log 2>&1
echo pg17073 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg29506.epub https://gutenberg.pglaf.org/cache/epub/29506/pg29506-images-3.epub >> pd.log 2>&1
echo pg29506 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg17223.epub https://gutenberg.pglaf.org/cache/epub/17223/pg17223-images-3.epub >> pd.log 2>&1
echo pg17223 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
curl.exe -sSL -f --connect-timeout 20 --max-time 300 -o pd\pg14765.epub https://gutenberg.pglaf.org/cache/epub/14765/pg14765-images-3.epub >> pd.log 2>&1
echo pg14765 exit=%errorlevel% >> pd.log
timeout /t 2 /nobreak > nul
echo FIN >> pd.log
exit
