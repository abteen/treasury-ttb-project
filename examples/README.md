# Description of Test Cases


1. `bulk`: Test wine and beer label bulk upload. Error in Beer ABV (application data), OCR (missing period). Wine ABV detected correctly, mismatch up to agent discretion (can manually override). Wine net contents not detected, can be manually input. 
2. `malt_all_pass`: Test malt single image.  All fields match application data, but application data has error in government warning.
3. `malt_non_numeric_issue`: Test malt single image. ABV given warning as numerical values match but wording doesn't
4. `wine_prediction`: Mismatch in ABV, option to override and mark correct
5. `wine_prediction_abv_error`: Actual error in ABV value. 