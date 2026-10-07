// Creer une requete vide nommee fxOlistCsv et y coller cette fonction.
// Le chemin est Windows puisque Power BI Desktop tourne sous Windows.
(FileName as text) as table =>
let
    Root = "C:/CHANGE_ME/olist-data-analysis/data/",
    Source = Csv.Document(File.Contents(Root & FileName),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    EmptyToNull = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers))
in
    EmptyToNull

// Dans d'AUTRES requetes vides, utiliser les expressions suivantes.
// FactOrders :
// = fxOlistCsv("fact_orders.csv")
// FactItems :
// = fxOlistCsv("fact_items.csv")
// DimProducts :
// = fxOlistCsv("dim_products.csv")
// DimSellers :
// = fxOlistCsv("dim_sellers.csv")
// Cohorts :
// = fxOlistCsv("customer_cohorts.csv")
