export default function ExpoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 overflow-y-auto bg-gray-50" style={{ marginLeft: 0 }}>
      {children}
    </div>
  );
}
