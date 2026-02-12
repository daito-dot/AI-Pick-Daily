import { PageHeader } from '@/components/ui';
import MarketTabs from '@/components/MarketTabs';
import { ModelOutputsContent } from '@/components/models';
import { getAvailableDates, getModelOutputs } from '@/lib/supabase';

export const revalidate = 300;

export default async function ModelsPage() {
  const [usDates, jpDates] = await Promise.all([
    getAvailableDates('us'),
    getAvailableDates('jp'),
  ]);

  const [usOutputs, jpOutputs] = await Promise.all([
    usDates[0] ? getModelOutputs(usDates[0], 'us') : Promise.resolve([]),
    jpDates[0] ? getModelOutputs(jpDates[0], 'jp') : Promise.resolve([]),
  ]);

  const usContent = (
    <ModelOutputsContent
      initialDates={usDates}
      initialOutputs={usOutputs}
      marketType="us"
    />
  );

  const jpContent = (
    <ModelOutputsContent
      initialDates={jpDates}
      initialOutputs={jpOutputs}
      marketType="jp"
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Outputs"
        subtitle="各AIモデルの判断結果をシンボル別に比較"
      />
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
