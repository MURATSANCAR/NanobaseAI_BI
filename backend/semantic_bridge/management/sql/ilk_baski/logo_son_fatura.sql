-- Logo'daki en son fatura günü. Tahmin son TAM aydan başlar: o gün ayın son günü değilse o ay yarımdır.
SELECT MAX(s.[Fatura Tarihi]) AS son_fatura
FROM {satis:-1} AS s
