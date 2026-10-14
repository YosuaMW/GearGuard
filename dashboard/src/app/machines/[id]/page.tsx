import { MachineDetail } from "./MachineDetail";

// Static export needs every machine page listed at build time.
// Add an id here when a machine is added to the line.
export function generateStaticParams() {
  return ["m1", "m2", "m3", "m4"].map((id) => ({ id }));
}

export default async function MachinePage({ params }: PageProps<"/machines/[id]">) {
  const { id } = await params;
  return <MachineDetail id={id} />;
}
