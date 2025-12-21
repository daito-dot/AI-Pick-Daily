import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AI Pick Daily',
  description: 'AIによる毎日の株式銘柄レコメンド',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen">
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold text-primary-700">
                AI Pick Daily
              </h1>
              <nav className="flex gap-6">
                <a href="/" className="text-gray-600 hover:text-primary-600">
                  Today
                </a>
                <a href="/history" className="text-gray-600 hover:text-primary-600">
                  History
                </a>
                <a href="/performance" className="text-gray-600 hover:text-primary-600">
                  Performance
                </a>
              </nav>
            </div>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">
          {children}
        </main>
        <footer className="border-t mt-12 py-6 text-center text-gray-500 text-sm">
          <p>AI Pick Daily - Educational purposes only. Not financial advice.</p>
        </footer>
      </body>
    </html>
  );
}
