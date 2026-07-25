import datetime
import sys

# Cấu hình UTF-8 cho sys.stdout để tránh lỗi mã hóa trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=== DANH SÁCH 5 MẸO TỐI ƯU CODE ===")
    print(f"Thời gian hiện tại: {now}\n")

    tips = [
        "1. Sử dụng đúng cấu trúc dữ liệu (VD: dùng set/dict thay vì list khi tra cứu O(1)).",
        "2. Hạn chế tính toán trùng lặp (Caching / Memoization kết quả đắt đỏ).",
        "3. Tận dụng List Comprehension & Generator expressions trong Python.",
        "4. Ưu tiên biến cục bộ và hạn chế tối đa việc sử dụng biến toàn cục.",
        "5. Giữ code rõ ràng, mô-đun hóa và tránh tối ưu quá sớm (Avoid premature optimization)."
    ]

    for tip in tips:
        print(tip)

if __name__ == "__main__":
    main()
