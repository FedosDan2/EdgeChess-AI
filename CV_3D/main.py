from pipeline.pipeline import ChessPipeline


def main():
    # Пути
    MODEL_PATH = "/home/fedosdan2/Study/EdgeChess-AI/CV_3D/weights/best_3d_detection.pt"
    IMAGE_PATH = "/home/fedosdan2/Study/EdgeChess-AI/CV_3D/data/images/test/rgb_3_original.jpg"

    # Создаём пайплайн
    pipeline = ChessPipeline(
        model_path=MODEL_PATH,
        confidence=0.5,
        output_size=900,
        padding=50,
    )

    # Обрабатываем
    try:
        results = pipeline.process(IMAGE_PATH, save_results=True)

        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ")
        print("=" * 60)
        print("\n📊 Доска:")
        print(results["board_state"])
        print(f"\n♟️  FEN: {results['fen']}")
        print("=" * 60)

    except Exception as e:
        print(f" Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()