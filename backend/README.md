# functions to add 

# get list of the events with the date as a parameter
/api/getEventsDay/[date]

-> [{
    id: UUID,

}, ...]

# get a list of events starting from the starting date as a parameter (so starts from here, and then all the next dates as well)
/api/getEventsFromDay/[date]

/api/fetchFavorites
/api/