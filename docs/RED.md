# Red: misma LAN o redes distintas

Todos los nodos hablan con **un solo servidor NATS** que corre en el PC principal (puerto TCP **4222**). Los demás PCs solo necesitan poder llegar a ese puerto. El dashboard usa el puerto **8000** y el monitoreo de NATS el **8222**.

## Opción A: misma red local (LAN / Wi-Fi)

1. En el PC principal, averigua su IP: `ipconfig` → "Dirección IPv4" (p. ej. `192.168.1.50`).
2. Abre los puertos en el firewall de Windows (PowerShell como administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "Bolsa NATS" -Direction Inbound -Protocol TCP -LocalPort 4222 -Action Allow
   New-NetFirewallRule -DisplayName "Bolsa Dashboard" -Direction Inbound -Protocol TCP -LocalPort 8000,8222 -Action Allow
   ```
3. Desde otro PC prueba la conexión: `Test-NetConnection 192.168.1.50 -Port 4222` debe decir `TcpTestSucceeded : True`.
4. Arranca cada nodo con `pc_nodo.bat <nodo> 192.168.1.50 <token>`.

Problemas comunes: redes Wi-Fi de universidad con "aislamiento de clientes" (los PCs no se ven entre sí) o perfil de red "Pública" en Windows. En esos casos usa la opción B.

## Opción B (recomendada como respaldo): Tailscale

Tailscale crea una VPN en malla cifrada (WireGuard) entre los 5 PCs aunque estén en casas o redes distintas, sin abrir puertos en el router. El plan personal es gratis.

1. Instala Tailscale en los 5 PCs (https://tailscale.com/download) e inicia sesión con la misma cuenta (o invita a los compañeros a tu tailnet).
2. En el PC principal mira su IP de Tailscale: `tailscale ip -4` (algo como `100.101.102.103`).
3. Arranca los nodos apuntando a esa IP: `pc_nodo.bat tunja 100.101.102.103 <token>`.
4. El dashboard queda en `http://100.101.102.103:8000` para todos.

Con Tailscale el firewall de Windows igual debe permitir el puerto 4222 (regla de la opción A).

## Otras alternativas

- **ZeroTier:** similar a Tailscale.
- **Túnel TCP** (ngrok, Cloudflare Tunnel, playit.gg): exponen el puerto 4222 a internet; útil si no se puede instalar VPN, pero agrega latencia. Usa siempre token.
- **Clúster NATS:** para la versión final se puede correr NATS en 2 o 3 PCs en clúster, así la red sobrevive aunque se caiga el principal (bloque `cluster {}` en `despliegue/nats.conf`).

## Seguridad

- Usa siempre un token (`NATS_TOKEN`), el mismo en todos los PCs. Sin token cualquiera en la red podría publicar órdenes.
- No subas el token al repositorio.

## Qué medir para la sustentación

- `red_ms` por nodo (dashboard y `analitica/reporte.py`): latencia de ida y vuelta menos cómputo.
- Comparar LAN vs Tailscale vs túnel con la misma corrida.
- Monitoreo de NATS en `http://IP_PRINCIPAL:8222/varz` y `/connz` (conexiones, mensajes, bytes).
