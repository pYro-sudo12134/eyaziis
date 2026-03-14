docker run --name postgres-dictionary \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -v myvolume:/app \
  -d postgres:15-alpine