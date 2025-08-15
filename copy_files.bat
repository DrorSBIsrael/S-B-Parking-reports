@echo off
echo Copying files to correct locations...

REM Copy HTML to templates
echo Copying parking_subscribers.html to templates...
copy /Y parking_subscribers.html templates\parking_subscribers.html

REM Copy JavaScript files to static/js
echo Copying JavaScript files to static/js...
copy /Y config.js static\js\config.js
copy /Y parking-api-xml.js static\js\parking-api-xml.js
copy /Y parking-ui-integration-xml.js static\js\parking-ui-integration-xml.js

echo Done! Files copied successfully.
pause


