# Arquitectura y protocolo

## Ciclo de un tick (1 tick = 1 día hábil)

1. El **coordinador** publica `sim.tick` con el número de tick, la fecha hábil y los choques nuevos.
2. Cada **nodo**:
   - El `internacional` calcula el mundo (tasas por país, petróleo, demanda externa, TRM) y publica `mundo`.
   - El `colombia` corre la junta del Banco de la República (cada 21 ticks) y publica `politica.colombia`.
   - Liquida las ejecuciones que le llegaron (`fills`) y procesa su economía: salarios, impuestos, consumo, ventas, crédito, quiebras, contratación, emprendimiento, inflación.
   - Corre el mercado: formador de liquidez, inversionistas (núcleo Monte Carlo paralelo), operadores de ruido y las órdenes que llegaron de otros nodos.
   - Envía sus órdenes a otros nodos (`ordenes.<destino>`), devuelve las ejecuciones (`fills.<origen>`) y publica `estado.<nodo>`, `eventos.<nodo>` y `sim.ack.<nodo>`.
3. El coordinador espera los `ack` de todos los nodos vivos (máx. `timeout_ack_s`). Quien no responde suma un fallo; con 3 fallos queda **caído** y la simulación continúa sin él.

## Mensajes (NATS, JSON)

| Asunto | Emite | Contenido |
|---|---|---|
| `sim.quien` | coordinador | pide a los nodos que se anuncien |
| `sim.hola.<nodo>` | nodo | anuncio al arrancar o reconectar |
| `sim.tick` | coordinador | `t`, `fecha`, `choques[]`, `enviado` (marca de tiempo) |
| `sim.ack.<nodo>` | nodo | `t`, `ms` de cómputo, `enviado` (para medir la red) |
| `sim.global` | coordinador | estado de los nodos, latencias, ticks/s |
| `estado.<nodo>` | nodo | activos (vela OHLC, precio, μ, σ, reglas), regiones, indicadores |
| `ordenes.<destino>` | nodo origen | lote de órdenes: agente, ticker, lado, cantidad, límite, ref, país |
| `fills.<origen>` | nodo destino | por orden: cantidad ejecutada, costo, moneda, motivo de rechazo |
| `politica.colombia` | nodo colombia | tasa de intervención, inflación y desempleo nacionales |
| `mundo` | nodo internacional | TRM, petróleo, demanda externa, tasas, aranceles |
| `eventos.<nodo>` | nodos y coordinador | quiebras, nuevas empresas, insolvencias, caídas, choques |
| `control.choque` / `control.pausa` / `control.velocidad` | dashboard | órdenes del usuario |

## Órdenes entre nodos (comercio distribuido)

- Al crear una orden el agente **reserva** efectivo (compra) o acciones (venta). Para activos de otro nodo la reserva incluye la conversión de moneda con la TRM, el impuesto a extranjeros y un margen del 3%.
- El nodo destino valida con **sus reglas** (p. ej. China limita la propiedad extranjera al 30%), mezcla la orden con las locales y la cruza en su libro.
- La ejecución vuelve por `fills.<origen>`; el origen entrega las acciones y devuelve lo no usado.
- Si el destino está caído, la reserva se devuelve a los 20 ticks.
- Los flujos de capital de Colombia hacia el exterior mueven la TRM.

## Modelo económico (resumen)

- **Hogares:** salario diario indexado al nivel de precios, impuesto de renta, consumo con propensión que baja si suben las tasas, ahorro, deuda de consumo e insolvencia si la deuda supera 8 salarios.
- **Empresas:** venden según su capacidad (productividad × empleados), pagan nómina, intereses, costos e impuesto de renta de su país; contratan o despiden según ventas; piden crédito hasta un apalancamiento máximo; **quiebran** si no consiguen crédito o llevan más de 60 días en pérdidas con patrimonio negativo.
- **Emprendimiento:** hogares con ahorro e inversionistas fundan empresas (salida a bolsa con su propio ticker).
- **Bancos:** prestan su liquidez y cobran tasa de política + spread; una crisis financiera recorta el crédito.
- **Gobierno por región:** recauda y gasta; paga subsidio de desempleo.
- **Sector externo:** exportaciones ligadas a la TRM, a la demanda de los socios comerciales (con aranceles) y, para petróleo y minería, al precio del crudo.
- **Inflación:** base observada + brecha de demanda + traspaso de la TRM − efecto de la tasa de interés.
- **Precios:** subasta doble continua; formador de liquidez anclado al valor fundamental (patrimonio y rentabilidad); inversionistas con Monte Carlo (retorno esperado − aversión × (CVaR 5% + caída máxima)).

## Reglas por país (`config/escenario.json`)

`reglas_base` aplica a todos; `reglas_paises` sobrescribe por país; cada región puede tener `reglas` propias. Hoy incluye: renta empresarial por país, impuesto de renta personal, spread bancario, apalancamiento máximo, tope de propiedad extranjera, impuesto a transacciones de extranjeros (p. ej. IOF de Brasil), aranceles a productos colombianos (TLC, Alianza del Pacífico), subsidio de desempleo, propensión a consumir y probabilidad de emprender.

## Choques disponibles

`crisis_financiera`, `pandemia`, `crisis_internacional`, `boom_consumo`, `inflacion`, `subida_tasas`, `bajada_tasas`, `boom_petrolero`, `guerra_comercial`, `fin_guerra_comercial`. Se aplican en el mismo tick en todos los nodos (o en uno solo, con `objetivo`), con magnitud y duración.
