// JP Stock name mapping
export const JP_STOCK_NAMES: Record<string, string> = {
  "7203.T": "トヨタ",
  "6758.T": "ソニーG",
  "9984.T": "ソフトバンクG",
  "6861.T": "キーエンス",
  "9432.T": "NTT",
  "8306.T": "三菱UFJ",
  "6902.T": "デンソー",
  "9433.T": "KDDI",
  "7267.T": "ホンダ",
  "6501.T": "日立",
  "8035.T": "東京エレクトロン",
  "6594.T": "日本電産",
  "7974.T": "任天堂",
  "4063.T": "信越化学",
  "6098.T": "リクルート",
  "4385.T": "メルカリ",
  "4478.T": "フリー",
  "6920.T": "レーザーテック",
  "6857.T": "アドバンテスト",
  "8058.T": "三菱商事",
  "4502.T": "武田薬品",
  "8031.T": "三井物産",
  "6367.T": "ダイキン",
  "6971.T": "京セラ",
  "9983.T": "ファストリ",
  "4519.T": "中外製薬",
  "6954.T": "ファナック",
  "8316.T": "三井住友FG",
  "6981.T": "村田製作所",
  "7751.T": "キヤノン",
  "4568.T": "第一三共",
  "8766.T": "東京海上",
  "7733.T": "オリンパス",
  "6988.T": "日東電工",
  "9020.T": "JR東日本",
  "4661.T": "オリエンタルランド",
  "8001.T": "伊藤忠",
  "6762.T": "TDK",
  "4503.T": "アステラス",
  "8802.T": "三菱地所",
  "9022.T": "JR東海",
  "4911.T": "資生堂",
  "6702.T": "富士通",
  "8411.T": "みずほFG",
  "8725.T": "MS&AD",
  "3659.T": "ネクソン",
  "9101.T": "日本郵船",
};

/**
 * Get display name for a stock symbol
 * For JP stocks (.T suffix), returns "会社名 (証券コード)"
 * For US stocks, returns the symbol as-is
 */
export function getStockDisplayName(symbol: string): string {
  if (symbol.endsWith('.T')) {
    const name = JP_STOCK_NAMES[symbol];
    return name ? `${name} (${symbol.replace('.T', '')})` : symbol;
  }
  return symbol;
}

/**
 * Check if a symbol is a Japanese stock
 */
export function isJPStock(symbol: string): boolean {
  return symbol.endsWith('.T');
}
