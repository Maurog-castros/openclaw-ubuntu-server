import argparse
from pathlib import Path

import pandas as pd


def build_monthly_report(csv_file: Path, target_month: str, output_file: Path) -> None:
    if not csv_file.exists():
        raise FileNotFoundError(f"No existe CSV: {csv_file}")

    df = pd.read_csv(csv_file)
    if df.empty:
        raise ValueError("El CSV esta vacio.")

    df["purchase_date"] = pd.to_datetime(df["purchase_date"], errors="coerce")
    df = df.dropna(subset=["purchase_date"])
    df["month"] = df["purchase_date"].dt.strftime("%Y-%m")

    month_df = df[df["month"] == target_month].copy()
    if month_df.empty:
        raise ValueError(f"No hay registros para el mes {target_month}")

    month_df["line_amount"] = pd.to_numeric(month_df["line_amount"], errors="coerce").fillna(0.0)
    month_df["ticket_total"] = pd.to_numeric(month_df["ticket_total"], errors="coerce").fillna(0.0)

    by_category = (
        month_df.groupby("category", as_index=False)["line_amount"]
        .sum()
        .sort_values("line_amount", ascending=False)
    )
    by_product = (
        month_df.groupby("product", as_index=False)["line_amount"]
        .sum()
        .sort_values("line_amount", ascending=False)
    )

    unique_tickets = month_df[["message_id", "ticket_total"]].drop_duplicates()
    total_spent = unique_tickets["ticket_total"].sum()
    tickets_count = unique_tickets["message_id"].nunique()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        f.write(f"# Informe gastos Lider - {target_month}\n\n")
        f.write(f"- Boletas detectadas: {tickets_count}\n")
        f.write(f"- Gasto total estimado: {total_spent:,.0f} CLP\n\n")

        f.write("## Gasto por categoria\n\n")
        for _, row in by_category.iterrows():
            f.write(f"- {row['category']}: {row['line_amount']:,.0f} CLP\n")

        f.write("\n## Top 20 productos por gasto\n\n")
        for _, row in by_product.head(20).iterrows():
            f.write(f"- {row['product']}: {row['line_amount']:,.0f} CLP\n")

    print(f"Reporte generado: {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera informe mensual de gastos Lider desde CSV.")
    parser.add_argument("--input", default="data/lider_receipts.csv", help="CSV de boletas parseadas.")
    parser.add_argument("--month", required=True, help="Mes en formato YYYY-MM")
    parser.add_argument(
        "--output",
        default="reports/lider_monthly_report.md",
        help="Ruta de salida del informe markdown.",
    )
    args = parser.parse_args()

    build_monthly_report(
        csv_file=Path(args.input),
        target_month=args.month,
        output_file=Path(args.output),
    )


if __name__ == "__main__":
    main()
