#!/bin/bash
cd /home/sudobreakstuff/routerconfig-tool
echo "Starting RouterConfig Pro..."

# Start backend
/home/sudobreakstuff/routerconfig-tool/backend/.venv/bin/python /home/sudobreakstuff/routerconfig-tool/backend/main.py &
sleep 2

# Start frontend
cd /home/sudobreakstuff/routerconfig-tool/frontend
npx vite --host 0.0.0.0 &
sleep 3

echo ""
echo "Backend:  http://127.0.0.1:7933"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"
wait
