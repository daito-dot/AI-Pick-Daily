import type { Metadata } from 'next';
import './globals.css';
import { NavBar } from '@/components/ui/NavBar';
import { getTodayBatchStatus } from '@/lib/supabase';

export const metadata: Metadata = {
  title: 'AI Pick Daily',
  description: 'AIによる毎日の株式銘柄レコメンド',
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const batchStatus = await getTodayBatchStatus();

  return (
    <html lang="ja">
      <body className="min-h-screen bg-surface-secondary">
        <NavBar systemStatus={batchStatus} />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          {children}
        </main>
        <footer className="border-t border-gray-100 mt-12 py-6 text-center text-gray-400 text-xs">
          AI Pick Daily — Educational purposes only. Not financial advice.
        </footer>
      </body>
    </html>
  );
}
