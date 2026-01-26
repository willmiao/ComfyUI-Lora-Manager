# Danbooru/E621 Tag Categories Reference

Reference for category values used in `danbooru_e621_merged.csv` tag files.

## Category Value Mapping

### Danbooru Categories

| Value | Description |
|-------|-------------|
| 0 | General |
| 1 | Artist |
| 2 | *(unused)* |
| 3 | Copyright |
| 4 | Character |
| 5 | Meta |

### e621 Categories

| Value | Description |
|-------|-------------|
| 6 | *(unused)* |
| 7 | General |
| 8 | Artist |
| 9 | Contributor |
| 10 | Copyright |
| 11 | Character |
| 12 | Species |
| 13 | *(unused)* |
| 14 | Meta |
| 15 | Lore |

## Danbooru Category Colors

| Description | Normal Color | Hover Color |
|-------------|--------------|-------------|
| General | #009be6 | #4bb4ff |
| Artist | #ff8a8b | #ffc3c3 |
| Copyright | #c797ff | #ddc9fb |
| Character | #35c64a | #93e49a |
| Meta | #ead084 | #f7e7c3 |

## CSV Column Structure

Each row in the merged CSV file contains 4 columns:

| Column | Description | Example |
|--------|-------------|---------|
| 1 | Tag name | `1girl`, `highres`, `solo` |
| 2 | Category value (0-15) | `0`, `5`, `7` |
| 3 | Post count | `6008644`, `5256195` |
| 4 | Aliases (comma-separated, quoted) | `"1girls,sole_female"`, empty string |

### Sample Data

```
1girl,0,6008644,"1girls,sole_female"
highres,5,5256195,"high_res,high_resolution,hires"
solo,0,5000954,"alone,female_solo,single,solo_female"
long_hair,0,4350743,"/lh,longhair"
mammal,12,3437444,"cetancodont,cetancodontamorph,feralmammal"
anthro,7,3381927,"adult_anthro,anhtro,antho,anthro_horse"
skirt,0,1557883,
```

## Source

- [PR #312: Add danbooru_e621_merged.csv](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete/pull/312)
- [DraconicDragon/dbr-e621-lists-archive](https://github.com/DraconicDragon/dbr-e621-lists-archive)
