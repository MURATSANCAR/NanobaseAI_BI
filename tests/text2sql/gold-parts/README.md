# Altın dosya parçaları

Her dosya bir soru aralığının altın girişlerini taşır (`part-<ilk>-<son>.json`, `{"cases": [...]}`), `answers-set100.json`
ile aynı biçimde. Parçalar gözden geçirilip ana dosyaya birleştirilir. Referans SQL bağımsız yazılır ve canlı
veritabanında en az bir kez koşturulur; köprünün ürettiği SQL kopyalanmaz.
