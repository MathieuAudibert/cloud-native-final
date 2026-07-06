#!/bin/bash

N=${1:-200}
BASE_URL="http://localhost:5000"

echo "Grafana  → http://localhost:3000  (admin/admin)"
echo "Jaeger   → http://localhost:16686"
echo "Prometheus → http://localhost:9090"
echo ""

items=("laptop" "phone" "tablet" "headphones" "keyboard" "monitor" "mouse" "webcam")

for i in $(seq 1 $N); do
  item=${items[$((RANDOM % ${#items[@]}))]}
  user_id="user-$((RANDOM % 20 + 1))"

  curl -s -X POST "$BASE_URL/api/order" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"$user_id\", \"item\": \"$item\"}" \
    -o /dev/null

  if [ $((RANDOM % 5)) -eq 0 ]; then
    curl -s "$BASE_URL/api/status" -o /dev/null
  fi

  if [ $((i % 20)) -eq 0 ]; then
    echo "[$i/$N] requêtes envoyées..."
  fi

  sleep 0.3
done

echo ""
echo "→ Ouvrir Grafana : http://localhost:3000/d/microservices-obs"
echo "→ Ouvrir Jaeger  : http://localhost:16686 → chercher 'service-a'"
