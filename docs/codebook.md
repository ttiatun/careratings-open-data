# Codebook

Every column carries a provenance tag:

- `cms`: Value taken from a CMS file unchanged except for type casting. U.S. government work, public domain.
- `tcr`: Value computed or curated by The Care Ratings from the CMS files. CC BY 4.0 (crosswalk table: CC0 1.0).

## Sources

| Key | CMS file | Notes |
| --- | --- | --- |
| `provider_info` | Provider Information | Care Compare nursing-home provider file; its Processing Date names the release. |
| `penalties` | Penalties | Fines and payment denials over the three-year lookback CMS publishes. |
| `ownership` | Ownership | Care Compare owner and manager roles per facility. |
| `enrollments` | Skilled Nursing Facility Enrollments | PECOS enrollment to CCN crosswalk. |
| `all_owners` | Skilled Nursing Facility All Owners | Every CMS-855A owner, officer and additional disclosable party with disclosure flags. |
| `chow` | Skilled Nursing Facility Change of Ownership | Buyer and seller enrollments for each change of ownership. |
| `chains` | Nursing Home Chain Performance Measures | Affiliated-entity performance file; the National row is the reconciliation target. |

## Definitions used in derived columns

- Ownership or control roles (CMS-855A role codes): 34, 35, 85, 86, 38, 39, 43. Additional disclosable parties (role 72), officers, directors and employees are not owners.
- Rescinded federal staffing minimums tested against reported hours: RN 0.55, nurse aide 2.45, total nurse 3.48 hours per resident per day.
- Release name: `v` + year and month of the Provider Information Processing Date.

## `facilities`

One row per Medicare/Medicaid-certified nursing home in the Care Compare Provider Information file, joined to its PECOS enrollment and ownership disclosures.

License: CC BY 4.0 for tcr columns; cms columns are public domain. Key: `ccn`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `ccn` | string | cms | Provider Information: CMS Certification Number (CCN) | Six-character CMS Certification Number. |
| `provider_name` | string | cms | Provider Information: Provider Name | Facility name as certified. |
| `address` | string | cms | Provider Information: Provider Address | Street address. |
| `city` | string | cms | Provider Information: City/Town | City or town. |
| `state` | string | cms | Provider Information: State | Two-letter state or territory code. |
| `zip_code` | string | cms | Provider Information: ZIP Code | ZIP code. |
| `county` | string | cms | Provider Information: County/Parish | County or parish. |
| `urban` | boolean | cms | Provider Information: Urban | Y/N urban flag as published by CMS. |
| `ownership_type` | string | cms | Provider Information: Ownership Type | CMS ownership type, e.g. 'For profit - Corporation'. |
| `ownership_category` | string | tcr | ownership_type before the ' - ' separator | 'For profit', 'Non profit', or 'Government'. |
| `provider_type` | string | cms | Provider Information: Provider Type | Medicare, Medicaid, or both. |
| `resides_in_hospital` | boolean | cms | Provider Information: Provider Resides in Hospital | Facility is located in a hospital. |
| `legal_business_name` | string | cms | Provider Information: Legal Business Name | Legal business name. |
| `date_first_certified` | date | cms | Provider Information: Date First Approved to Provide Medicare and Medicaid Services | First Medicare/Medicaid approval date. |
| `chain_id` | string | cms | Provider Information: Chain ID | CMS affiliated-entity id; joins to chains.chain_id. |
| `chain_name` | string | cms | Provider Information: Chain Name | CMS affiliated-entity name. |
| `chain_facility_count` | integer | cms | Provider Information: Number of Facilities in Chain | Facilities in the affiliated entity. |
| `continuing_care_retirement_community` | boolean | cms | Provider Information: Continuing Care Retirement Community | Part of a CCRC. |
| `special_focus_status` | string | cms | Provider Information: Special Focus Status | 'SFF', 'SFF Candidate', or empty. |
| `abuse_icon` | boolean | cms | Provider Information: Abuse Icon | CMS abuse icon displayed on Care Compare. |
| `inspection_over_2_years` | boolean | cms | Provider Information: Most Recent Health Inspection More Than 2 Years Ago | Most recent standard health inspection older than two years. |
| `ownership_changed_12mo` | boolean | cms | Provider Information: Provider Changed Ownership in Last 12 Months | CMS flag for an ownership change in the last 12 months. |
| `overall_rating` | integer | cms | Provider Information: Overall Rating | Five-Star overall rating, 1 to 5. |
| `health_inspection_rating` | integer | cms | Provider Information: Health Inspection Rating | Health inspection star rating. |
| `staffing_rating` | integer | cms | Provider Information: Staffing Rating | Staffing star rating. |
| `qm_rating` | integer | cms | Provider Information: QM Rating | Quality measure star rating. |
| `long_stay_qm_rating` | integer | cms | Provider Information: Long-Stay QM Rating | Long-stay quality measure rating. |
| `short_stay_qm_rating` | integer | cms | Provider Information: Short-Stay QM Rating | Short-stay quality measure rating. |
| `certified_beds` | integer | cms | Provider Information: Number of Certified Beds | Certified beds. |
| `avg_residents_per_day` | number | cms | Provider Information: Average Number of Residents per Day | Average daily census. |
| `reported_rn_hprd` | number | cms | Provider Information: Reported RN Staffing Hours per Resident per Day | Reported registered-nurse hours per resident per day (PBJ). |
| `reported_lpn_hprd` | number | cms | Provider Information: Reported LPN Staffing Hours per Resident per Day | Reported LPN hours per resident per day. |
| `reported_aide_hprd` | number | cms | Provider Information: Reported Nurse Aide Staffing Hours per Resident per Day | Reported nurse-aide hours per resident per day. |
| `reported_total_nurse_hprd` | number | cms | Provider Information: Reported Total Nurse Staffing Hours per Resident per Day | Reported total nurse hours per resident per day. |
| `weekend_total_nurse_hprd` | number | cms | Provider Information: Total number of nurse staff hours per resident per day on the weekend | Weekend total nurse hours per resident per day. |
| `adjusted_rn_hprd` | number | cms | Provider Information: Adjusted RN Staffing Hours per Resident per Day | Case-mix adjusted RN hours. |
| `adjusted_total_nurse_hprd` | number | cms | Provider Information: Adjusted Total Nurse Staffing Hours per Resident per Day | Case-mix adjusted total nurse hours. |
| `total_nurse_turnover_pct` | number | cms | Provider Information: Total nursing staff turnover | Total nursing staff turnover, percent. |
| `rn_turnover_pct` | number | cms | Provider Information: Registered Nurse turnover | RN turnover, percent. |
| `administrator_departures` | integer | cms | Provider Information: Number of administrators who have left the nursing home | Administrators who left in the reporting period. |
| `total_weighted_health_survey_score` | number | cms | Provider Information: Total Weighted Health Survey Score | Weighted health survey score (lower is better). |
| `infection_control_citations` | integer | cms | Provider Information: Number of Citations from Infection Control Inspections | Citations from infection-control inspections. |
| `num_fines` | integer | cms | Provider Information: Number of Fines | Fines in the lookback period. |
| `total_fines_dollars` | number | cms | Provider Information: Total Amount of Fines in Dollars | Fine dollars in the lookback period. |
| `num_payment_denials` | integer | cms | Provider Information: Number of Payment Denials | Payment denials in the lookback period. |
| `total_penalties` | integer | cms | Provider Information: Total Number of Penalties | Fines plus payment denials. |
| `latitude` | number | cms | Provider Information: Latitude | Latitude as geocoded by CMS. |
| `longitude` | number | cms | Provider Information: Longitude | Longitude as geocoded by CMS. |
| `processing_date` | date | cms | Provider Information: Processing Date | CMS release date of the Provider Information file; names the release. |
| `pecos_enrollment_id` | string | tcr | SNF Enrollments joined on CCN; the highest enrollment id wins when a CCN has several | Current PECOS enrollment id. |
| `affiliation_entity_id` | string | tcr | SNF Enrollments: AFFILIATION ENTITY ID via pecos_enrollment_id | PECOS affiliation entity id. |
| `affiliation_entity_name` | string | tcr | SNF Enrollments: AFFILIATION ENTITY NAME via pecos_enrollment_id | PECOS affiliation entity name. |
| `pecos_owner_rows` | integer | tcr | Count of SNF All Owners rows for pecos_enrollment_id | Owner, officer and party rows reported on CMS-855A. |
| `has_private_equity_owner` | boolean | tcr | SNF All Owners: PRIVATE EQUITY COMPANY - OWNER = Y on an ownership or control role (codes 34, 35, 85, 86, 38, 39, 43) | A disclosed owner or controller is flagged as a private equity company. |
| `has_reit_owner` | boolean | tcr | SNF All Owners: REIT - OWNER = Y on an ownership or control role | A disclosed owner or controller is flagged as a REIT. |
| `has_private_equity_party` | boolean | tcr | SNF All Owners: PRIVATE EQUITY COMPANY - OWNER = Y on any row | Any reported party, including landlords, lenders and vendors, is flagged as a private equity company. |
| `has_reit_party` | boolean | tcr | SNF All Owners: REIT - OWNER = Y on any row | Any reported party is flagged as a REIT (typically the property owner). |
| `private_equity_owner_names` | string | tcr | Distinct owner organization names behind has_private_equity_owner, joined with '; ' | Names of PE-flagged owners or controllers. |
| `reit_owner_names` | string | tcr | Distinct owner organization names behind has_reit_owner, joined with '; ' | Names of REIT-flagged owners or controllers. |
| `reit_party_names` | string | tcr | Distinct organization names behind has_reit_party, joined with '; ' | Names of REIT-flagged parties. |
| `last_chow_date` | date | tcr | SNF Change of Ownership: latest EFFECTIVE DATE where CCN - BUYER = ccn | Most recent change of ownership effective date. |
| `chow_count_36mo` | integer | tcr | SNF Change of Ownership events in the 36 months before processing_date | Changes of ownership in the 36 months before the release. |
| `meets_repealed_rn_floor` | boolean | tcr | reported_rn_hprd >= 0.55 | Reported RN hours meet the rescinded 2024 federal minimum (0.55 HPRD). NULL when hours are missing. |
| `meets_repealed_aide_floor` | boolean | tcr | reported_aide_hprd >= 2.45 | Reported nurse-aide hours meet the rescinded minimum (2.45 HPRD). |
| `meets_repealed_total_floor` | boolean | tcr | reported_total_nurse_hprd >= 3.48 | Reported total nurse hours meet the rescinded minimum (3.48 HPRD). |
| `meets_all_repealed_floors` | boolean | tcr | All three floor tests true | Meets every rescinded numeric minimum (the 24/7 RN requirement is not tested; it needs daily PBJ data). |

## `penalties`

One row per fine or payment denial in the Care Compare Penalties file (CMS's three-year lookback).

License: cms columns are public domain. Key: `ccn`, `penalty_date`, `penalty_type`, `fine_id`, `payment_denial_start_date`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `ccn` | string | cms | Penalties: CMS Certification Number (CCN) | Facility CCN. |
| `penalty_date` | date | cms | Penalties: Penalty Date | Date the penalty was imposed. |
| `penalty_type` | string | cms | Penalties: Penalty Type | 'Fine' or 'Payment Denial'. |
| `fine_id` | string | cms | Penalties: Fine ID | CMS fine identifier (fines only). |
| `fine_amount` | number | cms | Penalties: Fine Amount | Fine amount in dollars. |
| `payment_denial_start_date` | date | cms | Penalties: Payment Denial Start Date | Start of the payment denial (denials only). |
| `payment_denial_length_days` | integer | cms | Penalties: Payment Denial Length in Days | Length of the payment denial in days. |
| `processing_date` | date | cms | Penalties: Processing Date | CMS release date of the Penalties file. |

## `owners_carecompare`

Owner and manager roles per facility as shown on Care Compare (the Ownership file).

License: CC BY 4.0 for tcr columns; cms columns are public domain. Key: `ccn`, `role`, `owner_name`, `association_date_raw`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `ccn` | string | cms | Ownership: CMS Certification Number (CCN) | Facility CCN. |
| `role` | string | cms | Ownership: Role played by Owner or Manager in Facility | Role text. |
| `owner_type` | string | cms | Ownership: Owner Type | 'Individual' or 'Organization'. |
| `owner_name` | string | cms | Ownership: Owner Name | Owner or manager name. |
| `ownership_percentage_raw` | string | cms | Ownership: Ownership Percentage | Percentage as published, e.g. '5%' or 'NO PERCENTAGE PROVIDED'. |
| `ownership_pct` | number | tcr | ownership_percentage_raw parsed as a number when it is a percentage | Ownership percentage as a number, NULL when not provided. |
| `association_date_raw` | string | cms | Ownership: Association Date | Association date as published, e.g. 'since 01/25/2012'. |
| `association_date` | date | tcr | association_date_raw parsed after the word 'since' | Association date. |
| `processing_date` | date | cms | Ownership: Processing Date | CMS release date of the Ownership file. |

## `owners_pecos`

Every owner, officer, managing employee and additional disclosable party reported on Form CMS-855A for a skilled nursing facility enrollment, with the disclosure flags CMS publishes since November 2024.

License: CC BY 4.0 for tcr columns; cms columns are public domain. Key: `enrollment_id`, `owner_associate_id`, `role_code`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `enrollment_id` | string | cms | SNF All Owners: ENROLLMENT ID | PECOS enrollment id. |
| `ccn` | string | tcr | SNF Enrollments: CCN joined on ENROLLMENT ID | Facility CCN for the enrollment; NULL when the enrollment is not in the enrollments file. |
| `organization_name` | string | cms | SNF All Owners: ORGANIZATION NAME | Enrolled (operator) organization name. |
| `owner_associate_id` | string | cms | SNF All Owners: ASSOCIATE ID - OWNER | PECOS associate id of the owner or party. |
| `owner_type` | string | cms | SNF All Owners: TYPE - OWNER | 'I' individual or 'O' organization. |
| `role_code` | string | cms | SNF All Owners: ROLE CODE - OWNER | CMS role code. |
| `role_text` | string | cms | SNF All Owners: ROLE TEXT - OWNER | CMS role text. |
| `is_owner_role` | boolean | tcr | role_code in 34, 35, 85, 86, 38, 39, 43 | Row is an ownership or control role rather than an additional disclosable party, officer or employee. |
| `association_date` | date | cms | SNF All Owners: ASSOCIATION DATE - OWNER | Date the association began. |
| `owner_first_name` | string | cms | SNF All Owners: FIRST NAME - OWNER | Individual owner first name. |
| `owner_middle_name` | string | cms | SNF All Owners: MIDDLE NAME - OWNER | Individual owner middle name. |
| `owner_last_name` | string | cms | SNF All Owners: LAST NAME - OWNER | Individual owner last name. |
| `owner_title` | string | cms | SNF All Owners: TITLE - OWNER | Title of an individual. |
| `owner_organization_name` | string | cms | SNF All Owners: ORGANIZATION NAME - OWNER | Organization owner name. |
| `owner_dba_name` | string | cms | SNF All Owners: DOING BUSINESS AS NAME - OWNER | Organization owner DBA name. |
| `owner_city` | string | cms | SNF All Owners: CITY - OWNER | Owner city. |
| `owner_state` | string | cms | SNF All Owners: STATE - OWNER | Owner state. |
| `owner_zip_code` | string | cms | SNF All Owners: ZIP CODE - OWNER | Owner ZIP code. |
| `percentage_ownership` | number | cms | SNF All Owners: PERCENTAGE OWNERSHIP | Ownership percentage reported for the row. |
| `created_for_acquisition` | boolean | cms | SNF All Owners: CREATED FOR ACQUISITION - OWNER | Entity created for the acquisition. |
| `is_corporation` | boolean | cms | SNF All Owners: CORPORATION - OWNER | Owner is a corporation. |
| `is_llc` | boolean | cms | SNF All Owners: LLC - OWNER | Owner is an LLC. |
| `is_medical_provider_supplier` | boolean | cms | SNF All Owners: MEDICAL PROVIDER SUPPLIER - OWNER | Owner is a medical provider or supplier. |
| `is_management_services_company` | boolean | cms | SNF All Owners: MANAGEMENT SERVICES COMPANY - OWNER | Owner is a management services company. |
| `is_medical_staffing_company` | boolean | cms | SNF All Owners: MEDICAL STAFFING COMPANY - OWNER | Owner is a medical staffing company. |
| `is_holding_company` | boolean | cms | SNF All Owners: HOLDING COMPANY - OWNER | Owner is a holding company. |
| `is_investment_firm` | boolean | cms | SNF All Owners: INVESTMENT FIRM - OWNER | Owner is an investment firm. |
| `is_financial_institution` | boolean | cms | SNF All Owners: FINANCIAL INSTITUTION - OWNER | Owner is a financial institution. |
| `is_consulting_firm` | boolean | cms | SNF All Owners: CONSULTING FIRM - OWNER | Owner is a consulting firm. |
| `is_for_profit` | boolean | cms | SNF All Owners: FOR PROFIT - OWNER | Owner is for-profit. |
| `is_non_profit` | boolean | cms | SNF All Owners: NON PROFIT - OWNER | Owner is non-profit. |
| `is_private_equity_company` | boolean | cms | SNF All Owners: PRIVATE EQUITY COMPANY - OWNER | Owner is a private equity company, as reported by the facility. |
| `is_reit` | boolean | cms | SNF All Owners: REIT - OWNER | Owner is a real estate investment trust, as reported by the facility. |
| `is_chain_home_office` | boolean | cms | SNF All Owners: CHAIN HOME OFFICE - OWNER | Owner is a chain home office. |
| `is_trust_or_trustee` | boolean | cms | SNF All Owners: TRUST OR TRUSTEE - OWNER | Owner is a trust or trustee. |
| `is_other_type` | boolean | cms | SNF All Owners: OTHER TYPE - OWNER | Owner is another type. |
| `other_type_text` | string | cms | SNF All Owners: OTHER TYPE TEXT - OWNER | Description of the other type. |
| `is_parent_company` | boolean | cms | SNF All Owners: PARENT COMPANY - OWNER | Owner is a parent company. |
| `owned_by_another_org_or_ind` | boolean | cms | SNF All Owners: OWNED BY ANOTHER ORG OR IND - OWNER | Owner is itself owned by another organization or individual. |

## `changes_of_ownership`

Changes of ownership recorded in PECOS for skilled nursing facilities: buyer and seller enrollments with the effective date.

License: cms columns are public domain. Key: `buyer_enrollment_id`, `seller_enrollment_id`, `effective_date`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `buyer_enrollment_id` | string | cms | SNF Change of Ownership: ENROLLMENT ID - BUYER | Buyer enrollment id. |
| `buyer_ccn` | string | cms | SNF Change of Ownership: CCN - BUYER | Buyer CCN. |
| `buyer_npi` | string | cms | SNF Change of Ownership: NPI - BUYER | Buyer NPI. |
| `buyer_organization_name` | string | cms | SNF Change of Ownership: ORGANIZATION NAME - BUYER | Buyer organization. |
| `buyer_dba_name` | string | cms | SNF Change of Ownership: DOING BUSINESS AS NAME - BUYER | Buyer DBA name. |
| `buyer_state` | string | cms | SNF Change of Ownership: ENROLLMENT STATE - BUYER | Buyer enrollment state. |
| `chow_type_code` | string | cms | SNF Change of Ownership: CHOW TYPE CODE | Change type code. |
| `chow_type_text` | string | cms | SNF Change of Ownership: CHOW TYPE TEXT | Change type text. |
| `effective_date` | date | cms | SNF Change of Ownership: EFFECTIVE DATE | Effective date of the change. |
| `seller_enrollment_id` | string | cms | SNF Change of Ownership: ENROLLMENT ID - SELLER | Seller enrollment id. |
| `seller_ccn` | string | cms | SNF Change of Ownership: CCN - SELLER | Seller CCN. |
| `seller_npi` | string | cms | SNF Change of Ownership: NPI - SELLER | Seller NPI. |
| `seller_organization_name` | string | cms | SNF Change of Ownership: ORGANIZATION NAME - SELLER | Seller organization. |
| `seller_dba_name` | string | cms | SNF Change of Ownership: DOING BUSINESS AS NAME - SELLER | Seller DBA name. |
| `seller_state` | string | cms | SNF Change of Ownership: ENROLLMENT STATE - SELLER | Seller enrollment state. |

## `chains`

CMS Nursing Home Chain (affiliated entity) Performance Measures. The National row has chain_id 'NATIONAL'. After the fixed columns come the averaged quality measures exactly as CMS publishes them, with names normalized to snake_case; each release manifest lists them.

License: cms columns are public domain. Key: `chain_id`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `chain_id` | string | cms | Chain Performance: Chain ID ('NATIONAL' for the national row) | Affiliated-entity id; joins to facilities.chain_id. |
| `chain_name` | string | cms | Chain Performance: Chain | Affiliated-entity name. |
| `facility_count` | integer | cms | Chain Performance: Number of facilities | Facilities in the chain. |
| `state_count` | integer | cms | Chain Performance: Number of states and territories with operations | States and territories with facilities. |
| `sff_count` | integer | cms | Chain Performance: Number of Special Focus Facilities (SFF) | Special Focus Facilities. |
| `sff_candidate_count` | integer | cms | Chain Performance: Number of SFF candidates | SFF candidates. |
| `abuse_icon_count` | integer | cms | Chain Performance: Number of facilities with an abuse icon | Facilities with the abuse icon. |
| `abuse_icon_pct` | number | cms | Chain Performance: Percentage of facilities with an abuse icon | Percent with the abuse icon. |
| `pct_for_profit` | number | cms | Chain Performance: Percent of facilities classified as for-profit | Percent for-profit. |
| `pct_non_profit` | number | cms | Chain Performance: Percent of facilities classified as non-profit | Percent non-profit. |
| `pct_government` | number | cms | Chain Performance: Percent of facilities classified as government-owned | Percent government-owned. |
| `avg_overall_rating` | number | cms | Chain Performance: Average overall 5-star rating | Average overall rating. |
| `avg_health_inspection_rating` | number | cms | Chain Performance: Average health inspection rating | Average health inspection rating. |
| `avg_staffing_rating` | number | cms | Chain Performance: Average staffing rating | Average staffing rating. |
| `avg_qm_rating` | number | cms | Chain Performance: Average quality rating | Average quality measure rating. |
| `avg_total_nurse_hprd` | number | cms | Chain Performance: Average total nurse hours per resident day | Average total nurse hours per resident day. |
| `avg_weekend_nurse_hprd` | number | cms | Chain Performance: Average total weekend nurse hours per resident day | Average weekend nurse hours. |
| `avg_rn_hprd` | number | cms | Chain Performance: Average total Registered Nurse hours per resident day | Average RN hours. |
| `avg_nurse_turnover_pct` | number | cms | Chain Performance: Average total nursing staff turnover percentage | Average nursing staff turnover. |
| `avg_rn_turnover_pct` | number | cms | Chain Performance: Average Registered Nurse turnover percentage | Average RN turnover. |
| `avg_admin_departures` | number | cms | Chain Performance: Average number of administrators who have left the nursing home | Average administrator departures. |
| `total_fines` | integer | cms | Chain Performance: Total number of fines | Total fines. |
| `avg_fines` | number | cms | Chain Performance: Average number of fines | Average fines per facility. |
| `total_fines_dollars` | number | cms | Chain Performance: Total amount of fines in dollars | Total fine dollars. |
| `avg_fines_dollars` | number | cms | Chain Performance: Average amount of fines in dollars | Average fine dollars per facility. |
| `total_payment_denials` | integer | cms | Chain Performance: Total number of payment denials | Total payment denials. |
| `avg_payment_denials` | number | cms | Chain Performance: Average number of payment denials | Average payment denials per facility. |

Averaged quality-measure columns follow, named from the CMS headers; see the release manifest for the exact list.

## `state_summary`

Per-state aggregates computed from the facilities table, plus a national row with state 'US'. Descriptive statistics and the Care Quality Index components, exactly as the research page computes them.

License: CC BY 4.0. Key: `state`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `state` | string | tcr | facilities.state; 'US' for the national row | State or territory code. |
| `facility_count` | integer | tcr | count of facilities | Certified nursing homes. |
| `rated_facility_count` | integer | tcr | count of facilities with an overall rating | Facilities with a Five-Star overall rating. |
| `avg_overall_rating` | number | tcr | mean of overall_rating, rounded to 2 decimals | Average overall rating. |
| `pct_zero_penalty` | number | tcr | share of facilities with total_penalties = 0 or missing, in percent, 1 decimal | Percent of facilities with no fine or payment denial in the lookback period. |
| `pct_staffing_4plus` | number | tcr | share of rated facilities with staffing_rating >= 4, in percent, 1 decimal | Percent of staffing-rated facilities at 4 or 5 stars. |
| `care_quality_index` | integer | tcr | round(0.40 * (avg_overall_rating - 1) / 4 * 100 + 0.35 * pct_zero_penalty + 0.25 * pct_staffing_4plus); NULL below 10 facilities | The Care Ratings Care Quality Index, 0 to 100. |
| `pct_for_profit` | number | tcr | share of facilities with ownership_category = 'For profit' | Percent for-profit. |
| `pct_chain` | number | tcr | share of facilities with a chain_id | Percent in a CMS affiliated entity. |
| `facilities_pe_owner` | integer | tcr | count of has_private_equity_owner | Facilities with a disclosed private-equity owner or controller. |
| `facilities_reit_owner` | integer | tcr | count of has_reit_owner | Facilities with a disclosed REIT owner or controller. |
| `facilities_pe_party` | integer | tcr | count of has_private_equity_party | Facilities with any PE-flagged party. |
| `facilities_reit_party` | integer | tcr | count of has_reit_party | Facilities with any REIT-flagged party. |
| `sff_count` | integer | tcr | count of special_focus_status = 'SFF' | Special Focus Facilities. |
| `sff_candidate_count` | integer | tcr | count of special_focus_status = 'SFF Candidate' | SFF candidates. |
| `abuse_icon_count` | integer | tcr | count of abuse_icon | Facilities with the abuse icon. |
| `total_fines_dollars` | number | tcr | sum of total_fines_dollars | Fine dollars in the lookback period. |
| `avg_fines_per_facility` | number | tcr | total_fines_dollars / facility_count, rounded to 0 decimals | Fine dollars per facility. |
| `avg_reported_total_nurse_hprd` | number | tcr | mean of reported_total_nurse_hprd, 2 decimals | Average reported total nurse hours per resident per day. |
| `pct_meeting_repealed_total_floor` | number | tcr | share of facilities with reported hours where meets_repealed_total_floor is true, 1 decimal | Percent meeting the rescinded 3.48 HPRD total minimum. |
| `pct_meeting_all_repealed_floors` | number | tcr | share of facilities with reported hours where meets_all_repealed_floors is true, 1 decimal | Percent meeting all three rescinded numeric minimums. |
| `chow_count_12mo` | integer | tcr | changes of ownership with a buyer in the state in the 12 months before the release | Changes of ownership in the last 12 months. |

## `crosswalk`

Identifier crosswalk between Care Compare, PECOS and the CMS chain file. Released under CC0 1.0 so it can be reused in public knowledge bases.

License: CC0 1.0. Key: `ccn`.

| Column | Type | Provenance | Source | Description |
| --- | --- | --- | --- | --- |
| `ccn` | string | cms | Provider Information: CMS Certification Number (CCN) | Facility CCN. |
| `provider_name` | string | cms | Provider Information: Provider Name | Facility name. |
| `state` | string | cms | Provider Information: State | State. |
| `pecos_enrollment_id` | string | tcr | facilities.pecos_enrollment_id | Current PECOS enrollment id. |
| `npi` | string | tcr | SNF Enrollments: NPI via pecos_enrollment_id | National Provider Identifier of the enrollment. |
| `affiliation_entity_id` | string | tcr | facilities.affiliation_entity_id | PECOS affiliation entity id. |
| `chain_id` | string | cms | Provider Information: Chain ID | CMS affiliated-entity id. |
| `chain_name` | string | cms | Provider Information: Chain Name | CMS affiliated-entity name. |
