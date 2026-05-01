#!/bin/bash

case "$1" in
  up)
    docker-compose up -d
    echo "Wait 5s for DB to start..."
    sleep 5
    echo "Local database is up at localhost:5432"
    ;;
  down)
    docker-compose down
    ;;
  logs)
    docker-compose logs -f
    ;;
  shell)
    docker exec -it cashflow-db psql -U cashflow_user -d cashflow_local
    ;;
  sync)
    echo "Migrating data from SQLite..."
    ./venv/bin/python3 scratch/migrate_sqlite.py
    echo "Sync complete! (Reactive triggers have populated the forecasts)"
    ;;

  push)
    ./push_to_render.sh
    ;;
  *)
    echo "Usage: ./db.sh {up|down|logs|shell|sync|push}"
    ;;

esac
