'use client';

interface Props {
  dates: string[];
  selectedDate: string;
  onChange: (date: string) => void;
}

export default function DateSelector({ dates, selectedDate, onChange }: Props) {
  return (
    <select
      value={selectedDate}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
    >
      {dates.map((d) => (
        <option key={d} value={d}>
          {d}
        </option>
      ))}
    </select>
  );
}
