# 7. Надежный запуск с авто-устранением конфликта 409
if __name__ == "__main__":
    # Запуск Flask для удержания порта Render
    threading.Thread(target=run_web, daemon=True).start()
    
    print("⏳ Сброс старых соединений Telegram...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(3)  # Даем старому процессу Render 3 секунды на завершение
    except Exception as e:
        print(f"Сброс вебхука: {e}")

    print("🚀 Бот запущен и готов к работе!")

    # Цикл с автоматической защитой от ошибки 409
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                print("⚠️ Конфликт 409 (завершается старый процесс). Ждем 5 секунд...")
                time.sleep(5)
            else:
                print(f"⚠️ Ошибка API Telegram: {e}")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ Сетевой сбой: {e}")
            time.sleep(3)
