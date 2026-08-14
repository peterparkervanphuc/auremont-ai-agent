interface Props {
  size?: number;
  className?: string;
}

const ASPECT = 1938 / 1622;

// Linh vat thuong hieu Auremont — anh 3D nguoi dung cung cap (da tach nen
// trong suot + cat vien watermark), khong phai SVG tu ve nua. Ca robot cam
// tablet bang 2 tay (dinh trong 1 tam anh) nen KHONG the tach rieng canh tay
// de vay that — thay vao do dung CSS "nhay + nghieng nguoi" dinh ky
// (.auremont-mascot-greet) de tao cam giac chao/song dong tuong tu.
export function AuremontMascot({ size = 48, className }: Props) {
  return (
    <img
      src="/auremont-mascot.png"
      alt="Auremont AI"
      width={size}
      height={Math.round(size * ASPECT)}
      className={`auremont-mascot-greet ${className ?? ""}`}
      style={{ objectFit: "contain" }}
    />
  );
}
