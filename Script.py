import config
import time
from pybit.unified_trading import HTTP
from decimal import Decimal, ROUND_DOWN, ROUND_FLOOR
import numpy as np
import telebot
import threading

session = HTTP(
    testnet=False,
    api_key=config.api_key,
    api_secret=config.api_secret,
)


# DEFINIR PARAMETROS PARA OPERAR

symbol = input('INGRESE EL TICK A OPERAR: ').upper() + "USDT"
amount_usdt = Decimal(input('INGRESE LA CANTIDAD DE USDT PARA ABRIR LA POSICION: ')) 
factor_multiplicador_cantidad = Decimal(input('INGRESE EL PORCENTAJE DE INCREMENTO: ')) / Decimal('100')
numero_recompras = int(input('INGRESE LA CANTIDAD DE RECOMPRAS: '))
factor_multiplicador_distancia = Decimal(input('INGRESE LA DISTANCIA PARA LAS RECOMPRAS: '))
distancia_porcentaje_tp = Decimal(input('INGRESE LA DISTANCIA PARA EL TAKE PROFIT: ')) / Decimal('100') 
distancia_porcentaje_sl = Decimal (numero_recompras * factor_multiplicador_distancia /100 ) + Decimal("0.006") # DISTANCIA DEL STOP LOSS



bot_token = config.token_telegram
bot = telebot.TeleBot(bot_token)
chat_id = config.chat_id

def enviar_mensaje_telegram(chat_id, mensaje):
    try:
        bot.send_message(chat_id, mensaje)
    except Exception as e:
        print(f"No se pudo enviar el mensaje a Telegram: {e}")

def get_current_position(symbol):
    try:
        response_positions = session.get_positions(category="linear", symbol=symbol)
        if response_positions['retCode'] == 0:
            return response_positions['result']['list']
        else:
            return None
    except Exception as e:
        print(f"Error al obtener la posición: {e}")
        return None
    
def take_profit(symbol):
    # Obtener el precio de entrada de la posicion
    positions_list = get_current_position(symbol)
    current_price = Decimal(positions_list[0]['avgPrice'])

    # Convertir distancia_porcentaje_tp a Decimal
    distancia_porcentaje_tp_decimal = Decimal(str(distancia_porcentaje_tp))
    
    # Calcular el precio de take profit ajustado
    price_tp = adjust_price(symbol, current_price * (Decimal(1) + distancia_porcentaje_tp_decimal))
    
    # Colocar la orden de take profit
    response_limit_tp = session.place_order(
        category="linear",
        symbol=symbol,
        side="Sell",
        orderType="Limit",
        qty="0", 
        price=str(price_tp),
        reduceOnly=True,  # Esto asegura que la orden solo reducirá la posición existente
    )
    
    # Imprimir el resultado de la orden
    Mensaje_tp=(f"Take Profit para {symbol} colocado con éxito: {response_limit_tp}")
    enviar_mensaje_telegram(chat_id=chat_id, mensaje=Mensaje_tp)
    print(Mensaje_tp)
    

def abrir_posicion_largo(symbol, base_asset_qty_final, distancia_porcentaje_sl):
    try:
        positions_list = get_current_position(symbol)
        if positions_list and any(position['size'] != '0' for position in positions_list):
            print("Ya hay una posición abierta. No se abrirá otra posición.")
            return
        else:
            response_market_order = session.place_order(
                category="linear",
                symbol=symbol,
                side="Buy",
                orderType="Market",
                qty=base_asset_qty_final,
            )
            Mensaje_market=(f"Orden Market Long en {symbol} abierta con éxito: {response_market_order}")
            enviar_mensaje_telegram(chat_id=chat_id, mensaje=Mensaje_market)
            print(Mensaje_market)

            # Esperar hasta que la orden de mercado se complete
            time.sleep(5)  # Esperar 5 segundos (ajustar según sea necesario)

            # Verificar si la orden de mercado se completó correctamente
            if response_market_order['retCode'] != 0:
                print("Error al abrir la posición: La orden de mercado no se completó correctamente.")
                return
        

            # Obtener el precio de entrada de la posicion
            positions_list = get_current_position(symbol)
            current_price = Decimal(positions_list[0]['avgPrice'])


            price_sl = adjust_price(symbol, current_price * Decimal(1 - distancia_porcentaje_sl))
            stop_loss_order = session.set_trading_stop(
                category="linear",
                symbol=symbol,
                stopLoss=price_sl,
                slTriggerB="IndexPrice",
                tpslMode="Full",
                slOrderType="Market",
            )
            mensaje_sl=(f"Stop Loss para {symbol} colocado con éxito: {stop_loss_order}")
            enviar_mensaje_telegram(chat_id=chat_id, mensaje=mensaje_sl)
            print(mensaje_sl)

            size_nuevo= base_asset_qty_final

            # Abre órdenes límite con porcentajes de distancia y cantidad progresivos
            for i in range(1, numero_recompras + 1):
                porcentaje_distancia = Decimal('0.01') * i * factor_multiplicador_distancia  # Aumenta progresivamente
                cantidad_orden = size_nuevo * (1 + factor_multiplicador_cantidad)

                # Verifica si el tamaño nuevo tiene decimales
                if isinstance(size_nuevo, int):
                    cantidad_orden = int(cantidad_orden)  # Redondea hacia abajo si es un número entero
                else:
                    cantidad_orden = round(cantidad_orden, len(str(size_nuevo).split('.')[1]))

                size_nuevo = cantidad_orden  # Actualiza size para la siguiente iteración
                precio_orden_limite = adjust_price (symbol, current_price - (current_price * porcentaje_distancia))
                    
                # Coloca la orden límite
                response_limit_order = session.place_order(
                    category="linear",
                    symbol=symbol,
                    side="Buy",
                    orderType="Limit",
                    qty=str(cantidad_orden),
                    price=str(precio_orden_limite),
                )

                # Imprime la respuesta de la orden límite
                mensaje_recompras2=(f"{symbol}: Orden Límite de compra {i} colocada con exito:{response_limit_order}")
                enviar_mensaje_telegram(chat_id=chat_id, mensaje=mensaje_recompras2)
                print(mensaje_recompras2)

    except Exception as e:
        print(f"Error al abrir la posición: {e}")

def qty_step(symbol, amount_usdt):
    try:
        tickers = session.get_tickers(symbol=symbol, category="linear")
        for ticker_data in tickers["result"]["list"]:
            last_price = float(ticker_data["lastPrice"]) 
        
        last_price_decimal = Decimal(last_price)
        
        step_info = session.get_instruments_info(category="linear", symbol=symbol)
        qty_step = Decimal(step_info['result']['list'][0]['lotSizeFilter']['qtyStep'])

        base_asset_qty = amount_usdt / last_price_decimal

        qty_step_str = str(qty_step)
        if '.' in qty_step_str:
            decimals = len(qty_step_str.split('.')[1])
            base_asset_qty_final = round(base_asset_qty, decimals)
        else:
            base_asset_qty_final = int(base_asset_qty)

        return base_asset_qty_final
    except Exception as e:
        print(f"Error al calcular la cantidad del activo base: {e}")
        return None
    
def adjust_price(symbol, price):
    try:
        # Obtener la información del instrumento
        instrument_info = session.get_instruments_info(category="linear", symbol=symbol)
        tick_size = float(instrument_info['result']['list'][0]['priceFilter']['tickSize'])
        price_scale = int(instrument_info['result']['list'][0]['priceScale'])

        # Calcular el precio ajustado
        tick_dec = Decimal(f"{tick_size}")
        precision = Decimal(f"{10**price_scale}")
        price_decimal = Decimal(f"{price}")
        adjusted_price = (price_decimal * precision) / precision
        adjusted_price = (adjusted_price / tick_dec).quantize(Decimal('1'), rounding=ROUND_FLOOR) * tick_dec

        return float(adjusted_price)
    except Exception as e:
        print(f"Error al ajustar el precio: {e}")
        return None
    
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = deltas.copy()
    losses = deltas.copy()
    gains[gains < 0] = 0
    losses[losses > 0] = 0

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    rs = avg_gain / avg_loss if avg_loss != 0 else np.inf
    rsi = 100 - (100 / (1 + rs))

    for i in range(period, len(prices)):
        delta = deltas[i - 1]

        if delta > 0:
            avg_gain = (avg_gain * (period - 1) + delta) / period
            avg_loss = (avg_loss * (period - 1)) / period
        else:
            avg_loss = (avg_loss * (period - 1) - delta) / period
            avg_gain = (avg_gain * (period - 1)) / period

        rs = avg_gain / avg_loss if avg_loss != 0 else np.inf
        rsi = np.append(rsi, 100 - (100 / (1 + rs)))

    return rsi[-1]

def obtener_datos_kline(symbol):
    while True:
        response = session.get_kline(
            symbol=symbol,
            category="linear",
            interval=1,  # Intervalo de tiempo en minutos (ajusta según tu estrategia)
            limit=30,  
        )

        if response['retCode'] == 0:
            kline_data = response['result']['list']
            
            # Extraer los precios de cierre como números
            closes = [float(item[4]) for item in kline_data]  # El precio de cierre se encuentra en el índice 4
            
            # Calcular el RSI
            rsi_value = calculate_rsi(closes)
            
            # Redondear el valor del RSI a dos decimales
            rsi_value_rounded = round(rsi_value, 2)
            
            # Imprimir análisis del RSI
            print(f"El valor del RSI es: {rsi_value_rounded}")
            
            # Si el RSI es menor que el umbral, abrir posición larga
            if rsi_value < 150:
                print("RSI es menor que el umbral de sobreventa. Abriendo posición larga...")
                base_asset_qty_final = qty_step(symbol, amount_usdt)
                if base_asset_qty_final is not None:
                    abrir_posicion_largo(symbol, base_asset_qty_final, distancia_porcentaje_sl)
        
        # Esperar 1 minuto antes de verificar el RSI nuevamente
        time.sleep(60)

def cancelar_ordenes(symbol, precio_entrada_original):
    pnl_enviado = False  # Variable de control para verificar si ya se envió el mensaje de PNL
    while True:
        try:
            # Verificar si hay posición abierta
            positions_list = get_current_position(symbol)
            if positions_list and any(position['size'] != '0' for position in positions_list):
                # Restablecer pnl_enviado si se abre una nueva posición
                pnl_enviado = False
                # Calcular el precio de take profit ajustado
                current_price = Decimal(positions_list[0]['avgPrice'])
                if current_price != precio_entrada_original:
                    # Obtener órdenes límite abiertas para el take profit
                    open_orders_responsetp = session.get_open_orders(category="linear", symbol=symbol, openOnly=0, limit=1)

                    # Filtrar solo las órdenes límite para take profit
                    tp_limit_orders = None  # Establecer tp_limit_orders como None por defecto
                    if 'result' in open_orders_responsetp:
                        tp_limit_orders = [order for order in open_orders_responsetp['result'].get('list', [])
                                            if order.get('orderType') == "Limit" and order.get('side') == "Sell"]

                    # Verificar si hay órdenes límite para cancelar
                    if tp_limit_orders is not None:
                        # Iterar sobre las órdenes límite de take profit y cancelarlas
                        for order in tp_limit_orders:
                            take_profit_order_id = order['orderId']
                            cancel_response = session.cancel_order(category="linear", symbol=symbol, orderId=take_profit_order_id)
                            if 'result' in cancel_response and cancel_response['result']:   
                                mensaje_canceltp = f"Orden de take profit existente cancelada con éxito en {symbol}: {cancel_response}"
                                print(mensaje_canceltp)
                    # Actualizar el precio de entrada original con el precio de entrada actual
                    precio_entrada_original = current_price

                    # Colocar nuevamente el take profit
                    take_profit(symbol)
            else:
                # Cancelar todas las órdenes límite abiertas
                session.cancel_all_orders(category="linear", symbol=symbol)
                if not pnl_enviado:  # Verificar si el mensaje de PNL aún no se ha enviado
                    # Obtener la lista de órdenes cerradas y procesar la PNL
                    pnl_cerrada = float(session.get_closed_pnl(category="linear", symbol=symbol, side="Sell", limit=1)['result']['list'][0]['closedPnl'])
                    pnl_cerrada_round = round(pnl_cerrada, 2)
                    mensaje_pnl = f"Cerrando posición en {symbol}, 💰💰 PNL realizado 💰💰: {pnl_cerrada_round} USDT."
                    enviar_mensaje_telegram(chat_id=chat_id, mensaje=mensaje_pnl)
                    print(mensaje_pnl)
                    pnl_enviado = True  # Actualizar la variable de control a True
                

        except Exception as e:
            print(f"Error en la cancelación de órdenes: {e}")
        finally:
            # Esperar un tiempo antes de la próxima iteración
            time.sleep(2)

if __name__ == "__main__":
    # Obtener el precio de entrada original
    positions_list = get_current_position(symbol)
    precio_entrada_original = float(positions_list[0]['avgPrice'])
    
    # Crear y empezar los threads para obtener datos de Kline y cancelar órdenes
    kline_thread = threading.Thread(target=obtener_datos_kline, args=(symbol,))
    cancelar_ordenes_thread = threading.Thread(target=cancelar_ordenes, args=(symbol, precio_entrada_original))
    
    kline_thread.start()
    cancelar_ordenes_thread.start()
